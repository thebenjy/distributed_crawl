#!/usr/bin/env python3
"""
Automated Test Runner for Hybrid Crawler
Sets up mock websites and runs comprehensive tests
"""

import subprocess
import time
import json
import threading
import signal
import sys
from pathlib import Path
import requests
from test_setup import TestServerManager


class TestRunner:
    """Comprehensive test runner for hybrid crawler"""
    
    def __init__(self):
        self.server_manager = TestServerManager()
        self.test_results = {}
        self.servers_started = False
        
    def setup_signal_handler(self):
        """Setup signal handler for clean shutdown"""
        def signal_handler(sig, frame):
            print("\n🛑 Test interrupted by user")
            self.cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def start_test_servers(self):
        """Start the test web servers"""
        print("🚀 Starting test web servers...")
        self.server_manager.start_servers()
        self.servers_started = True
        
        # Verify servers are responding
        max_retries = 10
        for attempt in range(max_retries):
            try:
                normal_response = requests.get('http://localhost:8001/', timeout=2)
                geo_response = requests.get('http://localhost:8002/', timeout=2)
                
                if (normal_response.status_code == 200 and 
                    geo_response.status_code == 200 and 
                    'location not permitted' in geo_response.text.lower()):
                    print("✅ Test servers are ready")
                    return True
                    
            except requests.exceptions.RequestException:
                pass
            
            print(f"⏳ Waiting for servers to start... (attempt {attempt + 1}/{max_retries})")
            time.sleep(1)
        
        print("❌ Failed to start test servers")
        return False
    
    def create_test_files(self):
        """Create test configuration and URL files"""
        
        # Create test URLs file
        test_urls = [
            'http://localhost:8001/',          # Normal site home
            'http://localhost:8001/about',     # Normal site about
            'http://localhost:8001/services',  # Normal site services
            'http://localhost:8001/contact',   # Normal site contact
            'http://localhost:8002/',          # Geo-blocked home
            'http://localhost:8002/about',     # Geo-blocked about
            'http://localhost:8002/premium'    # Geo-blocked premium
        ]
        
        test_urls_file = Path('test_urls.txt')
        with open(test_urls_file, 'w') as f:
            for url in test_urls:
                f.write(f"{url}\n")
        
        print(f"📝 Created test URLs file: {test_urls_file}")
        return test_urls_file
    
    def run_crawler_test(self, test_name, args, expected_local=0, expected_lambda=0):
        """Run a single crawler test"""
        print(f"\n🧪 Running test: {test_name}")
        print("-" * 50)
        
        # Build command
        cmd = ['python3', 'hybrid_crawler.py'] + args
        print(f"Command: {' '.join(cmd)}")
        
        # Run test
        start_time = time.time()
        try:
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=120)  # 2 minute timeout
            
            execution_time = time.time() - start_time
            
            # Parse results
            if result.returncode == 0:
                print("✅ Crawler execution successful")
                
                # Try to find and parse the summary file
                results_dir = Path('crawl_output/results')
                if results_dir.exists():
                    summary_files = list(results_dir.glob('crawl_summary_*.json'))
                    if summary_files:
                        latest_summary = max(summary_files, key=lambda x: x.stat().st_mtime)
                        with open(latest_summary) as f:
                            summary = json.load(f)
                        
                        session = summary['crawl_session']
                        local_success = session.get('local_success', 0)
                        lambda_fallback = session.get('lambda_fallback', 0)
                        failures = session.get('failures', 0)
                        
                        print(f"📊 Results:")
                        print(f"   Local successes: {local_success}")
                        print(f"   Lambda fallbacks: {lambda_fallback}")
                        print(f"   Failures: {failures}")
                        print(f"   Execution time: {execution_time:.1f}s")
                        
                        # Check expectations
                        success = True
                        if expected_local > 0 and local_success < expected_local:
                            print(f"⚠️ Expected at least {expected_local} local successes, got {local_success}")
                            success = False
                        
                        if expected_lambda > 0 and lambda_fallback < expected_lambda:
                            print(f"⚠️ Expected at least {expected_lambda} lambda fallbacks, got {lambda_fallback}")
                            success = False
                        
                        test_result = {
                            'success': success,
                            'local_success': local_success,
                            'lambda_fallback': lambda_fallback,
                            'failures': failures,
                            'execution_time': execution_time,
                            'return_code': result.returncode
                        }
                        
                        if success:
                            print("✅ Test passed!")
                        else:
                            print("❌ Test failed expectations")
                            
                    else:
                        print("⚠️ No summary file found")
                        test_result = {'success': False, 'error': 'No summary file'}
                else:
                    print("⚠️ Results directory not found")
                    test_result = {'success': False, 'error': 'No results directory'}
                    
            else:
                print(f"❌ Crawler execution failed (exit code: {result.returncode})")
                print(f"Error output: {result.stderr}")
                test_result = {
                    'success': False,
                    'return_code': result.returncode,
                    'stderr': result.stderr,
                    'execution_time': execution_time
                }
            
        except subprocess.TimeoutExpired:
            print("❌ Test timed out")
            test_result = {'success': False, 'error': 'Timeout'}
            
        except Exception as e:
            print(f"❌ Test error: {e}")
            test_result = {'success': False, 'error': str(e)}
        
        self.test_results[test_name] = test_result
        return test_result.get('success', False)
    
    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("🧪 Hybrid Crawler Test Suite")
        print("=" * 50)
        
        # Create test files
        test_urls_file = self.create_test_files()
        
        # Test 1: Local-only mode (no AWS)
        print(f"\n📋 Test Plan:")
        print("1. Local crawling only (no Lambda)")
        print("2. Mixed crawling (with Lambda fallback)")
        print("3. High concurrency test")
        print("4. Custom output directory test")
        
        # Clear any existing output
        import shutil
        if Path('crawl_output').exists():
            shutil.rmtree('crawl_output')
        
        # Test 1: Local crawling only
        success_1 = self.run_crawler_test(
            "Local Crawling Only",
            ['--urls', str(test_urls_file), '--workers', '2', '--no-analysis'],
            expected_local=4  # Expect 4 localhost:8001 URLs to succeed locally
        )
        
        # Wait between tests
        time.sleep(2)
        
        # Test 2: With Lambda fallback (if AWS configured)
        import os
        if os.environ.get('AWS_ACCESS_KEY_ID'):
            success_2 = self.run_crawler_test(
                "Mixed Local/Lambda",
                ['--urls', str(test_urls_file), '--workers', '3'],
                expected_local=4,    # localhost:8001 URLs
                expected_lambda=3    # localhost:8002 URLs should trigger Lambda
            )
        else:
            print("\n⚠️ Skipping Lambda tests (AWS credentials not configured)")
            success_2 = True
        
        # Wait between tests
        time.sleep(2)
        
        # Test 3: High concurrency
        success_3 = self.run_crawler_test(
            "High Concurrency",
            ['--urls', str(test_urls_file), '--workers', '10', '--no-analysis'],
            expected_local=4
        )
        
        # Wait between tests
        time.sleep(2)
        
        # Test 4: Custom output directory
        success_4 = self.run_crawler_test(
            "Custom Output Directory",
            ['--urls', str(test_urls_file), '--output-dir', 'test_output', '--workers', '2'],
            expected_local=4
        )
        
        return all([success_1, success_2, success_3, success_4])
    
    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 60)
        print("🏁 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result.get('success', False))
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "N/A")
        print()
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
            print(f"{status} {test_name}")
            
            if 'execution_time' in result:
                print(f"      Execution time: {result['execution_time']:.1f}s")
            
            if 'local_success' in result:
                print(f"      Local: {result['local_success']}, Lambda: {result.get('lambda_fallback', 0)}")
            
            if not result.get('success', False) and 'error' in result:
                print(f"      Error: {result['error']}")
            
            print()
        
        print("📁 Output locations:")
        print("   - crawl_output/ (main test output)")
        print("   - test_output/ (custom directory test)")
        print("   - test_urls.txt (test URLs file)")
        print()
        
        if passed_tests == total_tests:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("⚠️ Some tests failed. Check the details above.")
        
        print("=" * 60)
    
    def cleanup(self):
        """Clean up test resources"""
        if self.servers_started:
            self.server_manager.stop_servers()
    
    def run(self):
        """Run the complete test suite"""
        self.setup_signal_handler()
        
        try:
            # Start test servers
            if not self.start_test_servers():
                print("❌ Failed to start test servers")
                return False
            
            # Run tests
            overall_success = self.run_all_tests()
            
            # Print summary
            self.print_test_summary()
            
            return overall_success
            
        except Exception as e:
            print(f"❌ Test suite error: {e}")
            return False
        finally:
            self.cleanup()


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test runner for hybrid crawler')
    parser.add_argument('--quick', action='store_true', help='Run quick test only')
    parser.add_argument('--no-lambda', action='store_true', help='Skip Lambda tests')
    
    args = parser.parse_args()
    
    print("🧪 Hybrid Crawler Automated Test Suite")
    print("======================================")
    print()
    
    # Check prerequisites
    prereqs_ok = True
    
    # Check if hybrid_crawler.py exists
    if not Path('hybrid_crawler.py').exists():
        print("❌ hybrid_crawler.py not found in current directory")
        prereqs_ok = False
    
    # Check Python packages
    try:
        import requests
        import aiohttp
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("   Run: pip install requests aiohttp")
        prereqs_ok = False
    
    if not prereqs_ok:
        print("\n❌ Prerequisites not met. Please fix the issues above.")
        return 1
    
    # Check optional packages
    optional_warnings = []
    
    try:
        import boto3
    except ImportError:
        optional_warnings.append("boto3 (Lambda fallback will be disabled)")
    
    import os
    if not os.environ.get('DEEPSEEK_API_KEY'):
        optional_warnings.append("DEEPSEEK_API_KEY not set (AI analysis will be disabled)")
    
    if not os.environ.get('AWS_ACCESS_KEY_ID'):
        optional_warnings.append("AWS credentials not set (Lambda fallback will be disabled)")
    
    if optional_warnings:
        print("⚠️ Optional components not available:")
        for warning in optional_warnings:
            print(f"   - {warning}")
        print()
    
    # Run tests
    runner = TestRunner()
    success = runner.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())