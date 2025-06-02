#!/usr/bin/env python3
"""
Lambda deployment script for the web crawler function
Creates deployment package and deploys to AWS Lambda
"""

import os
import sys
import json
import shutil
import zipfile
import subprocess
from pathlib import Path
import boto3
from botocore.exceptions import ClientError


class LambdaDeployer:
    """Deploy Lambda function with all dependencies"""
    
    def __init__(self, function_name: str, region: str = 'us-east-1'):
        self.function_name = function_name
        self.region = region
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.iam_client = boto3.client('iam', region_name=region)
        
        # Deployment configuration
        self.deployment_dir = Path('lambda_deployment')
        self.package_dir = self.deployment_dir / 'package'
        self.zip_file = self.deployment_dir / f'{function_name}.zip'
        
    def setup_deployment_directory(self):
        """Create and clean deployment directory"""
        if self.deployment_dir.exists():
            shutil.rmtree(self.deployment_dir)
        self.deployment_dir.mkdir()
        self.package_dir.mkdir()
        
    def install_dependencies(self):
        """Install Python dependencies for Lambda"""
        print("Installing dependencies...")
        
        # Lambda runtime dependencies
        lambda_requirements = [
            'crawl4ai>=0.2.0',
            'boto3>=1.26.0',
            'requests>=2.28.0',
            'beautifulsoup4>=4.11.0',
            'lxml>=4.9.0',
            'html2text>=2020.1.16',
            'playwright>=1.30.0'
        ]
        
        # Create requirements file
        req_file = self.deployment_dir / 'lambda_requirements.txt'
        with open(req_file, 'w') as f:
            f.write('\n'.join(lambda_requirements))
        
        # Install dependencies
        subprocess.run([
            sys.executable, '-m', 'pip', 'install',
            '-r', str(req_file),
            '-t', str(self.package_dir),
            '--no-cache-dir'
        ], check=True)
        
        print("Dependencies installed successfully")
        
    def copy_function_code(self):
        """Copy Lambda function code to package directory"""
        # Copy the main Lambda function
        shutil.copy('lambda_function.py', self.package_dir / 'lambda_function.py')
        
        # Create any additional modules if needed
        init_file = self.package_dir / '__init__.py'
        init_file.touch()
        
    def create_deployment_package(self):
        """Create ZIP deployment package"""
        print(f"Creating deployment package: {self.zip_file}")
        
        with zipfile.ZipFile(self.zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(self.package_dir):
                for file in files:
                    file_path = Path(root) / file
                    arc_name = file_path.relative_to(self.package_dir)
                    zipf.write(file_path, arc_name)
                    
        print(f"Package created: {self.zip_file} ({self.zip_file.stat().st_size / 1024 / 1024:.1f} MB)")
        
    def create_iam_role(self):
        """Create IAM role for Lambda function"""
        role_name = f"{self.function_name}-role"
        
        # Trust policy for Lambda
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            # Create role
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"IAM role for {self.function_name} Lambda function"
            )
            role_arn = response['Role']['Arn']
            
            # Attach basic Lambda execution policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
            )
            
            # Create and attach custom policy for S3 and Bedrock
            custom_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject"
                        ],
                        "Resource": [
                            "arn:aws:s3:::web-crawler-results/*"
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "bedrock:InvokeModel"
                        ],
                        "Resource": [
                            "arn:aws:bedrock:*:*:model/anthropic.claude-3-sonnet-20240229-v1:0"
                        ]
                    }
                ]
            }
            
            policy_name = f"{self.function_name}-policy"
            
            try:
                self.iam_client.create_policy(
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(custom_policy),
                    Description=f"Custom policy for {self.function_name}"
                )
                
                # Get account ID for policy ARN
                account_id = boto3.client('sts').get_caller_identity()['Account']
                policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"
                
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            except ClientError as e:
                if 'EntityAlreadyExists' in str(e):
                    print(f"Policy {policy_name} already exists")
                else:
                    raise
                    
            print(f"IAM role created: {role_arn}")
            return role_arn
            
        except ClientError as e:
            if 'EntityAlreadyExists' in str(e):
                # Role already exists, get its ARN
                response = self.iam_client.get_role(RoleName=role_name)
                role_arn = response['Role']['Arn']
                print(f"Using existing IAM role: {role_arn}")
                return role_arn
            else:
                raise
                
    def deploy_function(self):
        """Deploy Lambda function"""
        print(f"Deploying Lambda function: {self.function_name}")
        
        # Create IAM role
        role_arn = self.create_iam_role()
        
        # Read deployment package
        with open(self.zip_file, 'rb') as f:
            zip_content = f.read()
            
        function_config = {
            'FunctionName': self.function_name,
            'Runtime': 'python3.9',
            'Role': role_arn,
            'Handler': 'lambda_function.lambda_handler',
            'Code': {'ZipFile': zip_content},
            'Description': 'Web crawler and analyzer using Crawl4AI',
            'Timeout': 900,  # 15 minutes
            'MemorySize': 2048,  # 2GB
            'Environment': {
                'Variables': {
                    'PYTHONPATH': '/var/task:/opt/python'
                }
            }
        }
        
        try:
            # Try to create new function
            response = self.lambda_client.create_function(**function_config)
            print(f"Lambda function created successfully")
            
        except ClientError as e:
            if 'ResourceConflictException' in str(e):
                # Function exists, update it
                print("Function exists, updating...")
                
                # Update function code
                self.lambda_client.update_function_code(
                    FunctionName=self.function_name,
                    ZipFile=zip_content
                )
                
                # Update function configuration
                config_update = {k: v for k, v in function_config.items() 
                               if k not in ['FunctionName', 'Code']}
                self.lambda_client.update_function_configuration(**config_update)
                
                print("Lambda function updated successfully")
            else:
                raise
                
        # Wait for function to be ready
        print("Waiting for function to be ready...")
        waiter = self.lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=self.function_name)
        
        print(f"Lambda function {self.function_name} is ready!")
        
    def create_s3_bucket(self, bucket_name: str):
        """Create S3 bucket for storing results"""
        s3_client = boto3.client('s3', region_name=self.region)
        
        try:
            if self.region == 'us-east-1':
                s3_client.create_bucket(Bucket=bucket_name)
            else:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
            print(f"S3 bucket created: {bucket_name}")
            
        except ClientError as e:
            if 'BucketAlreadyExists' in str(e) or 'BucketAlreadyOwnedByYou' in str(e):
                print(f"S3 bucket already exists: {bucket_name}")
            else:
                raise
                
    def deploy(self):
        """Full deployment process"""
        print(f"Starting deployment of {self.function_name}...")
        
        # Setup
        self.setup_deployment_directory()
        
        # Install dependencies
        self.install_dependencies()
        
        # Copy function code
        self.copy_function_code()
        
        # Create package
        self.create_deployment_package()
        
        # Create S3 bucket
        self.create_s3_bucket('web-crawler-results')
        
        # Deploy function
        self.deploy_function()
        
        print(f"\nDeployment completed successfully!")
        print(f"Function name: {self.function_name}")
        print(f"Region: {self.region}")
        print(f"S3 bucket: web-crawler-results")
        
        # Cleanup
        if self.deployment_dir.exists():
            shutil.rmtree(self.deployment_dir)
            print("Cleanup completed")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy Lambda web crawler function')
    parser.add_argument('--function-name', default='web-crawler-analyzer',
                       help='Lambda function name')
    parser.add_argument('--region', default='us-east-1',
                       help='AWS region')
    
    args = parser.parse_args()
    
    deployer = LambdaDeployer(args.function_name, args.region)
    deployer.deploy()


if __name__ == "__main__":
    main()