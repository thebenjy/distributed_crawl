#!/usr/bin/env python3
"""
Hybrid Web Crawler - Local with Lambda Fallback
Performs multi-threaded local crawling with automatic Lambda fallback for geo-blocked content
Enhanced with descriptive filename generation including domain and page slugs
"""

import os,sys
import json
import time
import hashlib
import logging
import asyncio
import threading
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import argparse
import re

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
            'geo_blocked_skipped': 0,
            'start_time': None
        }
        
        # Error URL tracking
        self.error_urls = []
        self.error_urls_file = self.output_dir / 'error_urls.txt'
        
        # CSV data tracking
        self.csv_data = {}  # Store CSV row data by URL
        self.url_to_unique_id = {}  # Map URLs to unique IDs
        
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
                
    def generate_page_slug(self, url: str) -> str:
        """Generate a readable page slug from URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        path = parsed.path.strip('/')
        
        # Clean domain (remove special chars, keep only alphanumeric and dots)
        domain = re.sub(r'[^a-zA-Z0-9.-]', '', domain)
        domain = domain.replace('.', '_')
        
        # Process path
        if not path:
            page_name = 'index'
        else:
            # Remove file extensions and clean
            page_name = path.split('/')[-1]  # Get last part of path
            page_name = re.sub(r'\.[^.]*$', '', page_name)  # Remove extension
            if not page_name:
                page_name = path.replace('/', '_').strip('_')
            
        # Clean page name (alphanumeric, hyphens, underscores only)
        page_name = re.sub(r'[^a-zA-Z0-9-_]', '_', page_name)
        page_name = re.sub(r'_+', '_', page_name)  # Multiple underscores to single
        page_name = page_name.strip('_')
        
        if not page_name:
            page_name = 'page'
            
        # Combine domain and page name
        slug = f"{domain}_{page_name}"
        
        # Limit length and ensure it's valid
        slug = slug[:50]  # Reasonable filename length
        slug = slug.strip('_')
        
        return slug
    
    def generate_unique_id(self, lat: str, long: str, hash_length: int = 12) -> str:
        """Generate a unique alphanumeric ID from lat/long coordinates.
        
        Args:
            lat: Latitude.
            long: Longitude.
            hash_length: Length of the hash to generate.
            
        Returns:
            str: Unique hash ID.
        """
        slat = f"{lat}".strip()
        slong = f"{long}".strip()
        idata = f"{slat}{slong}"
        data = idata.encode('utf-8')
        hex_hash = hashlib.sha1(data).hexdigest()
        hash_id = hex_hash[:hash_length]
        logger.debug(f'Generated hash for {idata}: {hash_id}')
        return hash_id
    
    def load_csv_data(self, csv_file: str) -> List[str]:
        """Load URLs and metadata from CSV file"""
        urls = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # Detect dialect
                sample = f.read(1024)
                f.seek(0)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter
                
                reader = csv.DictReader(f, delimiter=delimiter)
                
                # Clean header names (strip whitespace)
                fieldnames = [field.strip() for field in reader.fieldnames]
                
                # Check for required columns
                site_column = None
                lat_column = None
                long_column = None
                unique_id_column = None
                
                # Find columns (case-insensitive)
                for field in fieldnames:
                    field_lower = field.lower()
                    if field_lower in ['site', 'url', 'website']:
                        site_column = field
                    elif field_lower in ['lat', 'latitude']:
                        lat_column = field
                    elif field_lower in ['long', 'lng', 'longitude']:
                        long_column = field
                    elif field_lower in ['uniqueid', 'unique_id', 'id']:
                        unique_id_column = field
                
                if not site_column:
                    raise ValueError("CSV must contain a 'site' or 'url' column")
                
                logger.info(f"CSV columns detected:")
                logger.info(f"  Site: {site_column}")
                logger.info(f"  Latitude: {lat_column}")
                logger.info(f"  Longitude: {long_column}")
                logger.info(f"  Unique ID: {unique_id_column}")
                
                # Process rows
                for row_num, row in enumerate(reader, start=2):
                    # Clean row data
                    clean_row = {k.strip(): v.strip() if v else '' for k, v in row.items()}
                    
                    url = clean_row.get(site_column, '').strip()
                    if not url:
                        logger.warning(f"Row {row_num}: Empty URL, skipping")
                        continue
                    
                    # Ensure URL has protocol
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                    
                    # Get or generate unique ID
                    unique_id = clean_row.get(unique_id_column, '').strip() if unique_id_column else ''
                    
                    if not unique_id and lat_column and long_column:
                        lat = clean_row.get(lat_column, '').strip()
                        long = clean_row.get(long_column, '').strip()
                        
                        if lat and long:
                            unique_id = self.generate_unique_id(lat, long)
                            logger.info(f"Generated unique ID for {url}: {unique_id}")
                        else:
                            logger.warning(f"Row {row_num}: Missing lat/long for {url}, using URL hash")
                            unique_id = hashlib.sha1(url.encode()).hexdigest()[:12]
                    elif not unique_id:
                        # Fallback: use URL hash
                        unique_id = hashlib.sha1(url.encode()).hexdigest()[:12]
                        logger.info(f"Generated URL-based unique ID for {url}: {unique_id}")
                    
                    # Store CSV data
                    self.csv_data[url] = clean_row
                    self.url_to_unique_id[url] = unique_id
                    urls.append(url)
                    
                    logger.debug(f"Loaded: {url} -> {unique_id}")
                
                logger.info(f"Loaded {len(urls)} URLs from CSV file: {csv_file}")
                
        except Exception as e:
            logger.error(f"Failed to load CSV file {csv_file}: {e}")
            raise
            
        return urls
        
    def get_enhanced_filename(self, url: str, content: str) -> Tuple[str, str]:
        """Generate enhanced filename with unique ID if available"""
        # Generate basic components
        md_hash = self.generate_content_hash(content)
        page_slug = self.generate_page_slug(url)
        
        # Check if we have unique ID from CSV
        unique_id = self.url_to_unique_id.get(url)
        
        if unique_id:
            # Format: uniqueid_hash_pageslug
            filename = f"{unique_id}_{md_hash}_{page_slug}"
        else:
            # Format: hash_pageslug (original format)
            filename = f"{md_hash}_{page_slug}"
            
        return filename, md_hash
        
    def generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]  # Use first 16 chars for shorter names
        
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
        """Fallback to Lambda for geo-blocked content (supports local SAM)"""
        if not self.lambda_client:
            raise Exception("Lambda client not available")
        
        # Check if we're using SAM local
        sam_local_endpoint = os.environ.get('SAM_LOCAL_LAMBDA_ENDPOINT', 'http://localhost:3001')
        use_sam_local = os.environ.get('USE_SAM_LOCAL', 'false').lower() == 'true'
        
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
            if use_sam_local:
                # Use SAM local Lambda endpoint
                logger.info(f"Using SAM local Lambda at {sam_local_endpoint}")
                
                # Create local Lambda client
                local_lambda_client = boto3.client(
                    'lambda',
                    endpoint_url=sam_local_endpoint,
                    region_name='us-east-1',
                    aws_access_key_id='dummy',
                    aws_secret_access_key='dummy'
                )
                
                response = local_lambda_client.invoke(
                    FunctionName='WebCrawlerFunction',
                    InvocationType='RequestResponse',
                    Payload=json.dumps(payload)
                )
            else:
                # Use deployed Lambda function
                response = self.lambda_client.invoke(
                    FunctionName=self.config.get('lambda_function_name', 'web-crawler-analyzer'),
                    InvocationType='RequestResponse',
                    Payload=json.dumps(payload)
                )
            
            response_payload = json.loads(response['Payload'].read())
            
            if response['StatusCode'] == 200 and response_payload.get('statusCode') == 200:
                body = response_payload.get('body', {})
                
                # Download markdown from S3 if available (skip for local testing)
                markdown_content = ""
                if body.get('s3_key') and self.s3_client and not use_sam_local:
                    try:
                        s3_response = self.s3_client.get_object(
                            Bucket=self.config.get('s3_bucket'),
                            Key=body['s3_key']
                        )
                        markdown_content = s3_response['Body'].read().decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Failed to download from S3: {e}")
                elif use_sam_local:
                    # For SAM local, markdown content is returned directly
                    markdown_content = body.get('markdown', '')
                        
                return {
                    'url': url,
                    'markdown': markdown_content,
                    'extracted_links': body.get('extracted_links', []),
                    'analysis': body.get('analysis', {}),
                    'md_hash': body.get('md_hash'),
                    's3_key': body.get('s3_key'),
                    'method': 'lambda_fallback_sam_local' if use_sam_local else 'lambda_fallback'
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
        """Save crawling result locally with enhanced filenames"""
        # Generate enhanced filename with unique ID if available
        filename, md_hash = self.get_enhanced_filename(url, result['markdown'])
        
        # Save markdown file
        markdown_file = self.markdown_dir / f"{filename}.md"
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(result['markdown'])
            
        # Prepare metadata with CSV data if available
        metadata = {
            'url': url,
            'md_hash': md_hash,
            'page_slug': self.generate_page_slug(url),
            'filename': filename,
            'crawled_at': datetime.now().isoformat(),
            'method': result.get('method', 'unknown'),
            'content_length': len(result['markdown']),
            'extracted_links': result.get('extracted_links', []),
            'analysis': result.get('analysis', {}),
            's3_key': result.get('s3_key'),
            'markdown_file': str(markdown_file.relative_to(self.output_dir))
        }
        
        # Add unique ID if available
        unique_id = self.url_to_unique_id.get(url)
        if unique_id:
            metadata['unique_id'] = unique_id
        
        # Add CSV data if available
        csv_row_data = self.csv_data.get(url)
        if csv_row_data:
            metadata['csv_data'] = csv_row_data
            
        # Save metadata
        metadata_file = self.results_dir / f"{filename}_metadata.json"
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
                logger.info(f"Geo-blocking detected for: {url}")
                
                # Check if Lambda is disabled
                if self.config.get('disable_lambda', False):
                    logger.info(f"Lambda disabled, skipping URL: {url}")
                    self.stats['geo_blocked_skipped'] += 1
                    
                    # Add to error URLs list
                    self.error_urls.append({
                        'url': url,
                        'reason': 'geo_blocked_lambda_disabled',
                        'timestamp': datetime.now().isoformat(),
                        'content_preview': local_result['markdown'][:200] + '...' if len(local_result['markdown']) > 200 else local_result['markdown']
                    })
                    
                    # Write to error file immediately
                    self.write_error_urls()
                    
                    return {
                        'url': url,
                        'status': 'skipped',
                        'reason': 'geo_blocked_lambda_disabled',
                        'method': 'local_geo_blocked',
                        'processing_time': time.time() - start_time,
                        'content_length': len(local_result['markdown']),
                        'links_extracted': len(local_result.get('extracted_links', [])),
                        'analysis_summary': 'Skipped due to geo-blocking (Lambda disabled)'
                    }
                else:
                    # Try Lambda fallback
                    logger.info(f"Trying Lambda fallback: {url}")
                    self.stats['lambda_fallback'] += 1
                    
                    try:
                        lambda_result = self.crawl_lambda_fallback(url)
                        result = lambda_result
                    except Exception as lambda_error:
                        logger.warning(f"Lambda fallback failed: {lambda_error}")
                        
                        # Add to error URLs list
                        self.error_urls.append({
                            'url': url,
                            'reason': 'lambda_fallback_failed',
                            'error': str(lambda_error),
                            'timestamp': datetime.now().isoformat()
                        })
                        self.write_error_urls()
                        
                        # Use local result despite geo-blocking
                        result = local_result
                        result['method'] = 'local_geo_blocked_lambda_failed'
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
            
            # Add to error URLs list
            self.error_urls.append({
                'url': url,
                'reason': 'processing_failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
            self.write_error_urls()
            
            return {
                'url': url,
                'status': 'failed',
                'error': str(e),
                'processing_time': time.time() - start_time
            }
            
            
    def write_error_urls(self):
        """Write error URLs to file"""
        try:
            with open(self.error_urls_file, 'w', encoding='utf-8') as f:
                f.write("# Error URLs - Failed or Skipped During Crawling\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write(f"# Total errors: {len(self.error_urls)}\n\n")
                
                for error_entry in self.error_urls:
                    f.write(f"# URL: {error_entry['url']}\n")
                    f.write(f"# Reason: {error_entry['reason']}\n")
                    f.write(f"# Timestamp: {error_entry['timestamp']}\n")
                    if 'error' in error_entry:
                        f.write(f"# Error: {error_entry['error']}\n")
                    if 'content_preview' in error_entry:
                        f.write(f"# Content Preview: {error_entry['content_preview']}\n")
                    f.write(f"{error_entry['url']}\n\n")
                    
            logger.info(f"Updated error URLs file: {self.error_urls_file} ({len(self.error_urls)} errors)")
            
        except Exception as e:
            logger.error(f"Failed to write error URLs file: {e}")
            
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
                'geo_blocked_skipped': self.stats['geo_blocked_skipped'],
                'failures': self.stats['failures'],
                'success_rate': ((self.stats['local_success'] + self.stats['lambda_fallback']) / self.stats['total_urls'] * 100) if self.stats['total_urls'] > 0 else 0,
                'lambda_disabled': self.config.get('disable_lambda', False),
                'error_urls_count': len(self.error_urls)
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
        if self.config.get('disable_lambda', False):
            print(f"Geo-blocked Skipped: {self.stats['geo_blocked_skipped']} (Lambda disabled)")
        print(f"Failures: {self.stats['failures']}")
        print(f"Success Rate: {summary['crawl_session']['success_rate']:.1f}%")
        print(f"Duration: {duration:.1f} seconds")
        print(f"Results saved to: {self.output_dir}")
        
        # Show error URLs info
        if self.error_urls:
            print(f"\n⚠️  Error URLs: {len(self.error_urls)}")
            print(f"   Error file: {self.error_urls_file}")
            print(f"   Reasons:")
            error_reasons = {}
            for error in self.error_urls:
                reason = error['reason']
                error_reasons[reason] = error_reasons.get(reason, 0) + 1
            for reason, count in error_reasons.items():
                print(f"     - {reason}: {count}")
        
        print(f"{'='*50}\n")
        
        # Show sample filenames generated
        markdown_files = list(self.markdown_dir.glob("*.md"))
        if markdown_files:
            print("📁 Sample generated filenames:")
            for i, file in enumerate(markdown_files[:5]):  # Show first 5 files
                print(f"   {file.name}")
            if len(markdown_files) > 5:
                print(f"   ... and {len(markdown_files) - 5} more files")
            print()


def main():
    parser = argparse.ArgumentParser(description='Hybrid Web Crawler - Local with Lambda Fallback')
    parser.add_argument('--urls', type=str, help='File containing URLs to crawl')
    parser.add_argument('--csv-import', type=str, help='CSV file with site column and optional lat/long for unique ID generation')
    parser.add_argument('--url-list', nargs='*', help='Direct URL list')
    parser.add_argument('--workers', type=int, default=5, help='Number of worker threads')
    parser.add_argument('--output-dir', type=str, default='crawl_output', help='Output directory')
    parser.add_argument('--s3-bucket', type=str, default='web-crawler-results-hybrid', help='S3 bucket name')
    parser.add_argument('--lambda-function', type=str, default='web-crawler-analyzer', help='Lambda function name')
    parser.add_argument('--no-analysis', action='store_true', help='Disable content analysis')
    parser.add_argument('--no-links', action='store_true', help='Disable link extraction')
    parser.add_argument('--disable-lambda', action='store_true', help='Disable Lambda fallback (write geo-blocked URLs to error file)')
    
    args = parser.parse_args()
    
    # Load URLs
    urls = []
    if args.csv_import:
        # Load from CSV file
        crawler_temp = HybridWebCrawler({'output_dir': 'temp'})  # Temp instance for CSV loading
        urls = crawler_temp.load_csv_data(args.csv_import)
        print(f"Loaded {len(urls)} URLs from CSV: {args.csv_import}")
        
        # Transfer CSV data to main crawler (will be created later)
        csv_data = crawler_temp.csv_data
        url_to_unique_id = crawler_temp.url_to_unique_id
        
    elif args.urls:
        with open(args.urls, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
        csv_data = {}
        url_to_unique_id = {}
    elif args.url_list:
        urls = args.url_list
        csv_data = {}
        url_to_unique_id = {}
    else:
        # Default test URLs
        urls = [
            'https://example.com',
            'https://httpbin.org/html',
            'https://docs.python.org/3/'
        ]
        csv_data = {}
        url_to_unique_id = {}
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
        'disable_lambda': args.disable_lambda,
        'timeout': 300
    }
    
    # Check environment and show warnings
    if args.disable_lambda:
        print("⚠️  Lambda fallback is DISABLED")
        print("   Geo-blocked URLs will be written to error_urls.txt")
    elif not os.environ.get('DEEPSEEK_API_KEY') and config['analyze_content']:
        print("Warning: DEEPSEEK_API_KEY not set, analysis will be skipped")
        
    # Run crawler
    crawler = HybridWebCrawler(config)
    
    # Transfer CSV data if loaded from CSV
    if args.csv_import:
        crawler.csv_data = csv_data
        crawler.url_to_unique_id = url_to_unique_id
        logger.info(f"Transferred CSV data for {len(csv_data)} URLs with unique IDs")
    
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