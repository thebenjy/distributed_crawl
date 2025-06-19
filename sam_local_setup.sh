#!/bin/bash

# SAM Local Setup Script for Web Crawler
# Sets up AWS SAM for local Lambda development and testing

set -e

echo "🚀 Setting up AWS SAM for Local Lambda Testing"
echo "=============================================="

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if SAM CLI is installed
if ! command_exists sam; then
    echo "❌ AWS SAM CLI not found"
    echo ""
    echo "📦 Installing AWS SAM CLI..."
    
    # Detect OS and install SAM CLI
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux installation
        echo "Installing SAM CLI for Linux..."
        wget -q https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-x86_64.zip
        unzip -q aws-sam-cli-linux-x86_64.zip -d sam-installation
        sudo ./sam-installation/install
        rm -rf sam-installation aws-sam-cli-linux-x86_64.zip
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS installation
        if command_exists brew; then
            echo "Installing SAM CLI via Homebrew..."
            brew tap aws/tap
            brew install aws-sam-cli
        else
            echo "Installing SAM CLI via pkg installer..."
            wget -q https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-macos-x86_64.pkg
            sudo installer -pkg aws-sam-cli-macos-x86_64.pkg -target /
            rm aws-sam-cli-macos-x86_64.pkg
        fi
    else
        echo "❌ Unsupported OS. Please install SAM CLI manually:"
        echo "   https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"
        exit 1
    fi
    
    echo "✅ SAM CLI installed successfully"
else
    echo "✅ AWS SAM CLI found: $(sam --version)"
fi

# Check if Docker is installed and running
if ! command_exists docker; then
    echo "❌ Docker not found"
    echo "SAM Local requires Docker to run Lambda functions locally"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running"
    echo "Please start Docker and try again"
    exit 1
fi

echo "✅ Docker is running"

# Check AWS CLI configuration
if ! command_exists aws; then
    echo "⚠️ AWS CLI not found - installing..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
        unzip -q awscliv2.zip
        sudo ./aws/install
        rm -rf aws awscliv2.zip
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command_exists brew; then
            brew install awscli
        else
            curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
            sudo installer -pkg AWSCLIV2.pkg -target /
            rm AWSCLIV2.pkg
        fi
    fi
fi

echo "✅ AWS CLI found: $(aws --version)"

# Create SAM project structure
echo ""
echo "📁 Setting up SAM project structure..."

# Create requirements.txt for Lambda dependencies
cat > requirements.txt << 'EOF'
# Core dependencies for Lambda function
boto3>=1.26.0
requests>=2.28.0
beautifulsoup4>=4.11.0
lxml>=4.9.0
html2text>=2020.1.16
aiohttp>=3.8.0

# Optional: Crawl4AI (may need special handling in Lambda)
# crawl4ai>=0.2.0
# playwright>=1.30.0
EOF

echo "✅ Created requirements.txt"

# Create local environment file
cat > .env.local << 'EOF'
# Local environment variables for SAM
DEEPSEEK_API_KEY=your-deepseek-api-key-here
AWS_DEFAULT_REGION=us-east-1

# Local S3 endpoint (if using LocalStack)
# AWS_ENDPOINT_URL_S3=http://localhost:4566
EOF

echo "✅ Created .env.local (edit with your API keys)"

# Create SAM local configuration
cat > samconfig.toml << 'EOF'
# SAM configuration for local development
version = 0.1

[default]
[default.local_start_api]
[default.local_start_api.parameters]
host = "0.0.0.0"
port = 3000
env_vars = ".env.local"
parameter_overrides = "DeepSeekApiKey=your-deepseek-api-key"

[default.local_start_lambda]
[default.local_start_lambda.parameters]
host = "0.0.0.0"
port = 3001
env_vars = ".env.local"

[default.local_invoke]
[default.local_invoke.parameters]
env_vars = ".env.local"

[default.build]
[default.build.parameters]
use_container = true
cached = true
parallel = true

[default.deploy]
[default.deploy.parameters]
stack_name = "web-crawler-sam"
region = "us-east-1"
confirm_changeset = true
capabilities = "CAPABILITY_IAM"
parameter_overrides = "DeepSeekApiKey=your-deepseek-api-key"
EOF

echo "✅ Created samconfig.toml"

# Create local test events
mkdir -p events

cat > events/test_crawl_event.json << 'EOF'
{
  "url": "https://example.com",
  "config": {
    "extract_links": true,
    "max_links": 5,
    "s3_bucket": "web-crawler-results-local",
    "timeout": 300,
    "analyze_content": true
  }
}
EOF

cat > events/localhost_test_event.json << 'EOF'
{
  "url": "http://host.docker.internal:8001/",
  "config": {
    "extract_links": true,
    "max_links": 10,
    "s3_bucket": "web-crawler-results-local",
    "timeout": 300,
    "analyze_content": false
  }
}
EOF

echo "✅ Created test event files in events/"

# Create Docker ignore file
cat > .dockerignore << 'EOF'
# Ignore files for Docker builds
.git
.gitignore
.dockerignore
Dockerfile
README.md
.env*
.venv
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
.pytest_cache/
.coverage
htmlcov/
node_modules/
.sam/
EOF

echo "✅ Created .dockerignore"

echo ""
echo "🔧 Environment Setup Instructions"
echo "================================="

echo ""
echo "1. Set your environment variables:"
echo "   Edit .env.local and set your DEEPSEEK_API_KEY"
echo ""
echo "2. Configure AWS credentials (for S3 access):"
echo "   aws configure"
echo "   # or export AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
echo ""

echo "🚀 SAM Local Commands"
echo "====================="

echo ""
echo "📦 Build the Lambda function:"
echo "   sam build"
echo ""
echo "🧪 Test Lambda function locally:"
echo "   sam local invoke WebCrawlerFunction -e events/test_crawl_event.json"
echo ""
echo "🌐 Start local API Gateway:"
echo "   sam local start-api"
echo "   # API available at: http://localhost:3000"
echo ""
echo "⚡ Start Lambda service locally:"
echo "   sam local start-lambda"
echo "   # Lambda service at: http://localhost:3001"
echo ""

echo "🧪 Test Commands"
echo "================"

echo ""
echo "Test with curl (after starting API):"
echo 'curl -X POST http://localhost:3000/crawl \'
echo '  -H "Content-Type: application/json" \'
echo '  -d @events/test_crawl_event.json'
echo ""

echo "Test with Python:"
cat > test_sam_local.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for SAM local Lambda function
"""

import json
import requests
import boto3

def test_local_api():
    """Test the local API Gateway endpoint"""
    url = "http://localhost:3000/crawl"
    
    payload = {
        "url": "https://example.com",
        "config": {
            "extract_links": True,
            "max_links": 5,
            "analyze_content": False
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_local_lambda():
    """Test direct Lambda invocation"""
    lambda_client = boto3.client(
        'lambda',
        endpoint_url='http://localhost:3001',
        region_name='us-east-1',
        aws_access_key_id='dummy',
        aws_secret_access_key='dummy'
    )
    
    payload = {
        "url": "https://httpbin.org/html",
        "config": {
            "extract_links": False,
            "analyze_content": False
        }
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='WebCrawlerFunction',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        print(f"Lambda Response: {result}")
        return response['StatusCode'] == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_sam_local.py [api|lambda]")
        sys.exit(1)
    
    test_type = sys.argv[1]
    
    if test_type == "api":
        print("Testing local API Gateway...")
        success = test_local_api()
    elif test_type == "lambda":
        print("Testing local Lambda...")
        success = test_local_lambda()
    else:
        print("Invalid test type. Use 'api' or 'lambda'")
        sys.exit(1)
    
    if success:
        print("✅ Test passed!")
    else:
        print("❌ Test failed!")
        sys.exit(1)
EOF

chmod +x test_sam_local.py
echo "✅ Created test_sam_local.py"

echo ""
echo "🎯 Quick Start"
echo "=============="
echo ""
echo "1. Edit .env.local with your API keys"
echo "2. sam build"
echo "3. sam local start-api &"
echo "4. python test_sam_local.py api"
echo ""

echo "✅ SAM Local setup completed!"
echo ""
echo "📖 Next steps:"
echo "   - Edit .env.local with your actual API keys"
echo "   - Run 'sam build' to build the Lambda function"
echo "   - Run 'sam local start-api' to start the local API"
echo "   - Test with the provided scripts"