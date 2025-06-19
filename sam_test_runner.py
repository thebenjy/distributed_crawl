#!/usr/bin/env python3
"""
SAM Local Test Runner for Hybrid Crawler
Integrates SAM local Lambda testing with the existing test framework
"""

import subprocess
import time
import json
import threading
import signal
import sys
import os
import requests
from pathlib import Path
from test_setup import TestServerManager


class SAMLocalManager:
    """Manages SAM local Lambda service for testing"""
    
    def __init__(self):
        self.sam_process = None
        self.api_process = None
        self.lambda_endpoint = "http://localhost:3001"
        self.api_endpoint = "http://localhost:3000"
        
    def start_sam_local_lambda(self):
        """Start SAM local Lambda service"""
        print("🚀 Starting SAM local Lambda service...")
        
        try:
            # Start Lambda service
            self.sam_process = subprocess.Popen(
                ['sam', 'local', 'start-lambda', '--host', '0.0.0.0', '--port', '3001'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for service to start
            max_retries = 30
            for attempt in range(max_retries):
                try:
                    response = requests.get(f"{self.lambda_endpoint}/2015-03-31/functions", timeout=2)
                    if response.status_code == 200:
                        print(f"✅ SAM local Lambda service started at {self.lambda_endpoint}")
                        return True
                except requests.exceptions.RequestException:
                    pass
                
                print(f"⏳ Waiting for SAM Lambda service... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
                
            print("❌ Failed to start SAM local Lambda service")
            return False
            
        except FileNotFoundError:
            print("❌ SAM CLI not found. Please install AWS SAM CLI first.")
            print("   Run: ./sam_local_setup.sh")
            return False
        except Exception as e:
            print(f"❌ Error starting SAM local Lambda: {e}")
            return False
    
    def start_sam_local_api(self):
        """Start SAM local API Gateway"""
        print("🌐 Starting SAM local API Gateway...")
        
        try:
            # Start API Gateway
            self.api_process = subprocess.Popen(
                ['sam', 'local', 'start-api', '--host', '0.0.0.0', '--port', '3000'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for service to start
            max_retries = 30
            for attempt in range(max_retries):
                try:
                    response = requests.get(f"{self.api_endpoint}/", timeout=2)
                    # API Gateway returns 403 for root path, which means it's running
                    if response.status_code in [200, 403, 404]:
                        print(f"✅ SAM local API Gateway started at {self.api_endpoint}")
                        return True
                except requests.exceptions.RequestException:
                    pass
                
                print(f"⏳ Waiting for SAM API Gateway... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
                
            print("❌ Failed to start SAM local API Gateway")
            return False
            
        except Exception as e:
            print(f"❌ Error starting SAM local API: {e}")
            return False
    
    def test_lambda_function(self, test_event):
        """Test Lambda function directly"""
        try:
            # Test direct Lambda invocation
            cmd = ['sam', 'local', 'invoke', 'WebCrawlerFunction', '--event', '-']
            
            process = subprocess.run(
                cmd,
                input=json.dumps(test_event),
                text=True,
                capture_output=True,
                timeout=60
            )
            
            if process.returncode == 0:
                try:
                    result = json.loads(process.stdout)
                    return {'success': True, 'result': result}
                except json.JSONDecodeError:
                    return {'success': False, 'error': 'Invalid JSON response', 'output': process.stdout}
            else:
                return {'success': False, 'error': process.stderr, 'output': process.stdout}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Lambda invocation timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def test_api_endpoint(self, test_payload):
        """Test API Gateway endpoint"""
        try:
            response = requests.post(
                f"{self.api_endpoint}/crawl",
                json=test_payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return {'success': True, 'result': response.json()}
            else:
                return {
                    'success': False, 
                    'error': f'API returned {response.status_code}',
                    'response': response.text
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def stop_services(self):
        """Stop SAM local services"""
        print("\n🛑 Stopping SAM local services...")
        
        if self.sam_process:
            self.sam_process.terminate()
            try:
                self.sam_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.sam_process.kill()
        
        if self.api_process:
            self.api_process.terminate()
            try:
                self.api_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.api_process.kill()
        
        print("✅ SAM local services stopped")


class SAMIntegratedTestRunner:
    """Test runner that integrates SAM local with the hybrid crawler tests"""
    
    def __init__(self):
        self.server_manager = TestServerManager()
        self.sam_manager = SAMLocalManager()
        self.test_results = {}
        
    def setup_signal_handler(self):
        """Setup signal handler for clean shutdown"""
        def signal_handler(sig, frame):
            print("\n🛑 Test interrupted by user")
            self.cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def check_prerequisites(self):
        """Check if all prerequisites are met"""
        print("🔍 Checking prerequisites...")
        
        # Check SAM CLI
        try:
            result = subprocess.run(['sam', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ SAM CLI: {result.stdout.strip()}")
            else:
                print("❌ SAM CLI not working properly")
                return False
        except FileNotFoundError:
            print("❌ SAM CLI not found")
            print("   Run: ./sam_local_setup.sh")
            return False
        
        # Check Docker
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Docker is running")
            else:
                print("❌ Docker is not running")
                return False
        except FileNotFoundError:
            print("❌ Docker not found")
            return False
        
        # Check if SAM template exists
        if not Path('template.yaml').exists():
            print("❌ SAM template.yaml not found")
            print("   Make sure you have the SAM template in the current directory")
            return False
        
        print("✅ SAM template.yaml found")
        
        # Check if Lambda function code exists
        if not Path('lambda_function.py').exists():
            print("❌ lambda_function.py not found")
            return False
        
        print("✅ lambda_function.py found")
        
        return True
    
    def build_sam_application(self):
        """Build the SAM application"""
        print("🔨 Building SAM application...")
        
        try:
            result = subprocess.run(
                ['sam', 'build', '--use-container'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode == 0:
                print("✅ SAM build successful")
                return True
            else:
                print(f"❌ SAM build failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ SAM build timeout")
            return False