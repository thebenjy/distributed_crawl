#!/usr/bin/env python3
"""
Hybrid Web Crawler - Local with Lambda Fallback
Performs multi-threaded local crawling with automatic Lambda fallback for geo-blocked content
"""

import os
import json
import time
import hashlib
import logging
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import argparse

import boto3
import requests
from botocore.exceptions import ClientError
import aiohttp
from bs4 import BeautifulSoup

# Try to import Crawl4AI, fallback to basic crawling if not available
try:
    from crawl4ai import AsyncWebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    print("Warning: Crawl4AI not available, using basic crawling")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hybrid_crawler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HybridWebCrawler:
    """Hybrid crawler that uses local processing with Lambda fallback"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.setup_aws_clients()
        self.setup_storage()
        
        # Trigger phrases for Lambda fallback
        self.geo_block_phrases = [
            'your location not permitted',
            'not available in your region',
            'geo-blocked',
            'location not supported',
            'access denied from your location',
            'content not available in your country',
            'vpn detected',
            'proxy detected'
        ]
        
        # Statistics
        self.stats = {
            'total_urls': 0,
            'local_success': 0,
            'lambda_fallback': 0,
            'failures': 0,
            'start_time': None
        }
        
    def setup_aws_clients(self):
        """Initialize AWS clients"""
        try:
            self.lambda_client = boto3.client('lambda', 
                region_name=self.config.get('aws_region', 'us-east-1'))
            self.s3_client = boto3.client('s3', 
                region_name=self.config.get('aws_region', 'us-east-1'))
            logger.info("AWS clients initialized")
        except Exception as e:
            logger.warning(f"AWS client initialization failed: {e}")
            self.lambda_client = None
            self.s3_client = None
            
    def setup_storage(self):
        """Setup local storage and S3 bucket"""
        # Create local directories
        self.output_dir = Path(self.config.get('output_dir', 'crawl_output'))
        self.markdown_dir = self.output_dir / 'markdown'
        self.results_dir = self.output_dir / 'results'
        
        for directory in [self.output_dir, self.markdown_dir, self.results_dir]:
            directory.mkdir(exist_ok=True)
            
        # Create S3 bucket if needed
        self.create_s3_bucket()
        
    def create_s3_bucket(self):
        """Create S3 bucket if it doesn't exist"""
        if not self.s3_client:
            logger.warning("S3 client not available, skipping bucket creation")
            return
            
        bucket_name = self.config.get('s3_bucket')
        if not bucket_name:
            logger.warning("No S3 bucket configured")
            return
            
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"S3 bucket '{bucket_name}' already exists")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                try:
                    # Create bucket
                    region = self.config.get('aws_region', 'us-east-1')
                    if region == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': region}
                        )
                    logger.info(f"Created S3 bucket: {bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create S3 bucket: {create_error}")
            else:
                logger.error(f"Error checking S3 bucket: {e}")
                
    def generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
        
    def is_geo_blocked(self, content: str) -> bool:
        """Check if content indicates geo-blocking"""
        content_lower = content.lower()
        return any(phrase in content_lower for phrase in self.geo_block_phrases)
        
    async def crawl_local_crawl4ai(self, url: str) -> Dict:
        """Crawl using Crawl4AI locally"""
        if not CRAWL4AI_AVAILABLE:
            raise Exception("Crawl4AI not available")
            
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(
                url=url,
                word_count_threshold=10,
                only_text=False,
                process_iframes=True,
                remove_overlay_elements=True,
                simulate_user=True,
                delay_before_return_html=2.0
            )
            
            if not result.success:
                raise Exception(f"Crawl failed: {result.error_message}")
                
            # Extract links
            extracted_links = []
            if result.links and self.config.get('extract_links', True):
                extracted_links = [link for link in result.links 
                                 if isinstance(link, str) and link.startswith('http')][:10]
                
            return {
                'url': url,
                'markdown': result.markdown or result.cleaned_html,
                'extracted_links': extracted_links,
                'status_code': result.status_code,
                'method': 'crawl4ai_local'
            }
            
    def crawl_local_basic(self, url: str) -> Dict:
        """Basic local crawling fallback"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Extract text content
        text_content = soup.get_text()
        lines = (line.strip() for line in text_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        markdown_content = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Extract links
        extracted_links = []
        if self.config.get('extract_links', True):
            links = soup.find_all('a', href=True)
            for link in links[:10]:  # Limit to 10 links
                href = link['href']
                if href.startswith('http'):
                    extracted_links.append(href)
                    
        return {
            'url': url,
            'markdown': markdown_content,
            'extracted_links': extracted_links,
            'status_code': response.status_code,
            'method': 'basic_local'
        }
        
    async def crawl_local(self, url: str) -> Dict:
        """Attempt local crawling with best available method"""
        try:
            if CRAWL4AI_AVAILABLE:
                return await self.crawl_local_crawl4ai(url)
            else:
                # Run basic crawling in thread pool since it's synchronous
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self.crawl_local_basic, url)
        except Exception as e:
            logger.error(f"Local crawling failed for {url}: {e}")
            raise
            
    def crawl_lambda_fallback(self, url: str) -> Dict:
        """Fallback to Lambda for geo-blocked content"""
        if not self.lambda_client:
            raise Exception("Lambda client not available")
            
        payload = {
            "url": url,
            "config": {
                "extract_links": self.config.get('extract_links', True),
                "max_links": 10,
                "s3_bucket": self.config.get('s3_bucket'),
                "timeout": self.config.get('timeout', 300),
                "analyze_content": self.config.get('analyze_content', True)
            }
        }
        
        try:
            response = self.lambda_client.invoke(
                FunctionName=self.config.get('lambda_function_name', 'web-crawler-analyzer'),
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            response_payload = json.loads(response['Payload'].read())
            
            if response['StatusCode'] == 200 and response_payload.get('statusCode') == 200:
                body = response_payload.get('body', {})
                
                # Download markdown from S3 if available
                markdown_content = ""
                if body.get('s3_key') and self.s3_client:
                    try:
                        s3_response = self.s3_client.get_object(
                            Bucket=self.config.get('s3_bucket'),
                            Key=body['s3_key']
                        )
                        markdown_content = s3_response['Body'].read().decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Failed to download from S3: {e}")
                        
                return {
                    'url': url,
                    'markdown': markdown_content,
                    'extracted_links': body.get('extracted_links', []),
                    'analysis': body.get('analysis', {}),
                    'md_hash': body.get('md_hash'),
                    's3_key': body.get('s3_key'),
                    'method': 'lambda_fallback'
                }
            else:
                raise Exception(f"Lambda invocation failed: {response_payload}")
                
        except Exception as e:
            logger.error(f"Lambda fallback failed for {url}: {e}")
            raise
            
    async def analyze_with_deepseek(self, content: str, url: str) -> Dict:
        """Analyze content with DeepSeek API"""
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not api_key:
            return {'error': 'DeepSeek API key not available'}
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""
        Analyze this web page content and return JSON:
        URL: {url}
        Content: {content[:4000]}
        
        Return JSON with: main_topic, content_type, summary, relevance_score (1-10), key_points (max 3)
        """
        
        payload = {
            "model": "deepseek-reasoner",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.1
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        analysis_text = result['choices'][0]['message']['content']
                        try:
                            return json.loads(analysis_text)
                        except:
                            return {'summary': analysis_text[:200]}
                    else:
                        return {'error': f'API error: {response.status}'}
        except Exception as e:
            return {'error': str(e)}
            
    def save_local_result(self, url: str, result: Dict) -> str:
        """Save crawling result locally"""
        # Generate hash
        md_hash = self.generate_content_hash(result['markdown'])
        
        # Save markdown file
        markdown_file = self.markdown_dir / f"{md_hash}.md"
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(result['markdown'])
            
        # Save metadata
        metadata = {
            'url': url,
            'md_hash': md_hash,
            'crawled_at': datetime.now().isoformat(),
            'method': result.get('method', 'unknown'),
            'content_length': len(result['markdown']),
            'extracted_links': result.get('extracted_links', []),
            'analysis': result.get('analysis', {}),
            's3_key': result.get('s3_key'),
            'markdown_file': str(markdown_file.relative_to(self.output_dir))
        }
        
        metadata_file = self.results_dir / f"{md_hash}_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        return md_hash
        
    async def process_single_url(self, url: str) -> Dict:
        """Process a single URL with local-first, Lambda fallback strategy"""
        start_time = time.time()
        
        try:
            # Step 1: Try local crawling
            logger.info(f"Attempting local crawl: {url}")
            local_result = await self.crawl_local(url)
            
            # Step 2: Check for geo-blocking
            if self.is_geo_blocked(local_result['markdown']):
                logger.info(f"Geo-blocking detected, trying Lambda fallback: {url}")
                self.stats['lambda_fallback'] += 1
                
                # Try Lambda fallback
                try:
                    lambda_result = self.crawl_lambda_fallback(url)
                    result = lambda_result
                except Exception as lambda_error:
                    logger.warning(f"Lambda fallback failed: {lambda_error}")
                    result = local_result  # Use local result despite geo-blocking
            else:
                logger.info(f"Local crawl successful: {url}")
                self.stats['local_success'] += 1
                result = local_result
                
            # Step 3: Analyze content if enabled
            if self.config.get('analyze_content', True) and not result.get('analysis'):
                logger.info(f"Analyzing content for: {url}")
                analysis = await self.analyze_with_deepseek(result['markdown'], url)
                result['analysis'] = analysis
                
            # Step 4: Save result locally
            md_hash = self.save_local_result(url, result)
            
            processing_time = time.time() - start_time
            
            return {
                'url': url,
                'status': 'success',
                'md_hash': md_hash,
                'method': result['method'],
                'processing_time': processing_time,
                'content_length': len(result['markdown']),
                'links_extracted': len(result.get('extracted_links', [])),
                'analysis_summary': result.get('analysis', {}).get('summary', 'No analysis')
            }
            
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
            self.stats['failures'] += 1
            
            return {
                'url': url,
                'status': 'failed',
                'error': str(e),
                'processing_time': time.time() - start_time
            }
            
    async def crawl_urls(self, urls: List[str]) -> Dict:
        """Crawl multiple URLs with threading"""
        self.stats['total_urls'] = len(urls)
        self.stats['start_time'] = datetime.now()
        
        logger.info(f"Starting crawl of {len(urls)} URLs with {self.config.get('max_workers', 5)} workers")
        
        # Process URLs concurrently
        semaphore = asyncio.Semaphore(self.config.get('max_workers', 5))
        
        async def process_with_semaphore(url):
            async with semaphore:
                return await self.process_single_url(url)
                
        tasks = [process_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Compile final results
        final_results = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results[urls[i]] = {
                    'status': 'failed',
                    'error': str(result)
                }
            else:
                final_results[urls[i]] = result
                
        # Save summary
        self.save_summary(final_results)
        
        return final_results
        
    def save_summary(self, results: Dict):
        """Save crawling summary"""
        end_time = datetime.now()
        duration = (end_time - self.stats['start_time']).total_seconds()
        
        summary = {
            'crawl_session': {
                'start_time': self.stats['start_time'].isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'total_urls': self.stats['total_urls'],
                'local_success': self.stats['local_success'],
                'lambda_fallback': self.stats['lambda_fallback'],
                'failures': self.stats['failures'],
                'success_rate': ((self.stats['local_success'] + self.stats['lambda_fallback']) / self.stats['total_urls'] * 100) if self.stats['total_urls'] > 0 else 0
            },
            'results': results,
            'config': self.config
        }
        
        summary_file = self.results_dir / f"crawl_summary_{int(time.time())}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
            
        logger.info(f"Summary saved to: {summary_file}")
        
        # Print stats
        print(f"\n{'='*50}")
        print(f"CRAWL SUMMARY")
        print(f"{'='*50}")
        print(f"Total URLs: {self.stats['total_urls']}")
        print(f"Local Success: {self.stats['local_success']}")
        print(f"Lambda Fallback: {self.stats['lambda_fallback']}")
        print(f"Failures: {self.stats['failures']}")
        print(f"Success Rate: {summary['crawl_session']['success_rate']:.1f}%")
        print(f"Duration: {duration:.1f} seconds")
        print(f"Results saved to: {self.output_dir}")
        print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description='Hybrid Web Crawler - Local with Lambda Fallback')
    parser.add_argument('--urls', type=str, help='File containing URLs to crawl')
    parser.add_argument('--url-list', nargs='*', help='Direct URL list')
    parser.add_argument('--workers', type=int, default=5, help='Number of worker threads')
    parser.add_argument('--output-dir', type=str, default='crawl_output', help='Output directory')
    parser.add_argument('--s3-bucket', type=str, default='web-crawler-results-hybrid', help='S3 bucket name')
    parser.add_argument('--lambda-function', type=str, default='web-crawler-analyzer', help='Lambda function name')
    parser.add_argument('--no-analysis', action='store_true', help='Disable content analysis')
    parser.add_argument('--no-links', action='store_true', help='Disable link extraction')
    
    args = parser.parse_args()
    
    # Load URLs
    urls = []
    if args.urls:
        with open(args.urls, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    elif args.url_list:
        urls = args.url_list
    else:
        # Default test URLs
        urls = [
            'https://example.com',
            'https://httpbin.org/html',
            'https://docs.python.org/3/'
        ]
        print("No URLs provided, using default test URLs")
        
    # Configuration
    config = {
        'max_workers': args.workers,
        'output_dir': args.output_dir,
        's3_bucket': args.s3_bucket,
        'lambda_function_name': args.lambda_function,
        'aws_region': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
        'analyze_content': not args.no_analysis,
        'extract_links': not args.no_links,
        'timeout': 300
    }
    
    # Check environment
    if not os.environ.get('DEEPSEEK_API_KEY') and config['analyze_content']:
        print("Warning: DEEPSEEK_API_KEY not set, analysis will be skipped")
        
    # Run crawler
    crawler = HybridWebCrawler(config)
    
    try:
        results = asyncio.run(crawler.crawl_urls(urls))
        print("Crawling completed successfully!")
        return 0
    except KeyboardInterrupt:
        print("\nCrawling interrupted by user")
        return 1
    except Exception as e:
        print(f"Crawling failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())