#!/usr/bin/env python3
"""
Local Orchestrator for Distributed Web Crawling
Manages AWS Lambda functions for crawling and analysis
"""

import json
import time
import hashlib
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import argparse
import sys

import boto3
from botocore.exceptions import ClientError
import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class CrawlStatus:
    """Status tracking for individual URLs"""
    status: str  # pending, in_progress, completed, failed
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    attempt_count: int = 0
    error: Optional[str] = None
    level: int = 0
    parent_url: Optional[str] = None
    md_hash: Optional[str] = None
    last_modified: Optional[str] = None
    s3_key: Optional[str] = None


@dataclass
class CrawlConfig:
    """Configuration for the crawling process"""
    max_levels: int = 1
    max_concurrency: int = 5
    retry_attempts: int = 3
    timeout: int = 900  # 15 minutes
    rate_limit_delay: float = 1.0
    debug_mode: bool = False
    debug_max_sublinks: int = 5
    debug_max_urls: int = 10
    lambda_function_name: str = "web-crawler-analyzer"
    s3_bucket: str = "web-crawler-results"
    aws_region: str = "us-east-1"


class LocalOrchestrator:
    """Main orchestrator class for managing distributed crawling"""
    
    def __init__(self, config: CrawlConfig):
        self.config = config
        self.setup_logging()
        self.setup_aws_clients()
        self.setup_storage_paths()
        
        # State management
        self.pending_urls: List[str] = []
        self.crawl_status: Dict[str, CrawlStatus] = {}
        self.crawl_results: Dict[str, dict] = {}
        self.processed_urls: Set[str] = set()
        
        # Concurrency control
        self.active_crawls = 0
        self.executor = ThreadPoolExecutor(max_workers=config.max_concurrency)
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO if not self.config.debug_mode else logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('crawler.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_aws_clients(self):
        """Initialize AWS clients"""
        try:
            self.lambda_client = boto3.client('lambda', region_name=self.config.aws_region)
            self.s3_client = boto3.client('s3', region_name=self.config.aws_region)
            self.logger.info("AWS clients initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS clients: {e}")
            raise
            
    def setup_storage_paths(self):
        """Create local storage directories"""
        self.storage_dir = Path("crawler_data")
        self.storage_dir.mkdir(exist_ok=True)
        
        self.local_markdown_dir = Path("local_markdown")
        self.local_markdown_dir.mkdir(exist_ok=True)
        
        # State files
        self.pending_urls_file = self.storage_dir / "pending_urls.json"
        self.crawl_status_file = self.storage_dir / "crawl_status.json"
        self.crawl_results_file = self.storage_dir / "crawl_results.json"
        
    def load_state(self):
        """Load existing state from JSON files"""
        # Load pending URLs
        if self.pending_urls_file.exists():
            with open(self.pending_urls_file, 'r') as f:
                self.pending_urls = json.load(f)
                
        # Load crawl status
        if self.crawl_status_file.exists():
            with open(self.crawl_status_file, 'r') as f:
                status_data = json.load(f)
                self.crawl_status = {
                    url: CrawlStatus(**data) for url, data in status_data.items()
                }
                
        # Reset in_progress to pending (interrupted crawls)
        for url, status in self.crawl_status.items():
            if status.status == "in_progress":
                status.status = "pending"
                self.logger.info(f"Reset interrupted crawl for {url}")
                
        # Load crawl results
        if self.crawl_results_file.exists():
            with open(self.crawl_results_file, 'r') as f:
                self.crawl_results = json.load(f)
                
        # Update processed URLs set
        self.processed_urls = {
            url for url, status in self.crawl_status.items() 
            if status.status in ["completed", "failed"]
        }
        
        self.logger.info(f"Loaded state: {len(self.pending_urls)} pending, "
                        f"{len(self.processed_urls)} processed")
                        
    def save_state(self):
        """Save current state to JSON files"""
        # Save pending URLs
        with open(self.pending_urls_file, 'w') as f:
            json.dump(self.pending_urls, f, indent=2)
            
        # Save crawl status
        status_data = {url: asdict(status) for url, status in self.crawl_status.items()}
        with open(self.crawl_status_file, 'w') as f:
            json.dump(status_data, f, indent=2)
            
        # Save crawl results
        with open(self.crawl_results_file, 'w') as f:
            json.dump(self.crawl_results, f, indent=2)
            
    def add_urls(self, urls: List[str], level: int = 0, parent_url: str = None):
        """Add URLs to the pending queue"""
        for url in urls:
            if url not in self.crawl_status and url not in self.processed_urls:
                self.pending_urls.append(url)
                self.crawl_status[url] = CrawlStatus(
                    status="pending",
                    level=level,
                    parent_url=parent_url
                )
                
    def invoke_lambda(self, url: str) -> dict:
        """Invoke Lambda function for a single URL"""
        payload = {
            "url": url,
            "config": {
                "extract_links": self.crawl_status[url].level < self.config.max_levels - 1,
                "max_links": self.config.debug_max_sublinks if self.config.debug_mode else None,
                "s3_bucket": self.config.s3_bucket,
                "timeout": self.config.timeout
            }
        }
        
        try:
            response = self.lambda_client.invoke(
                FunctionName=self.config.lambda_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            response_payload = json.loads(response['Payload'].read())
            
            if response['StatusCode'] == 200:
                return response_payload
            else:
                raise Exception(f"Lambda invocation failed: {response_payload}")
                
        except Exception as e:
            self.logger.error(f"Lambda invocation error for {url}: {e}")
            raise
            
    def process_url(self, url: str) -> bool:
        """Process a single URL through Lambda"""
        status = self.crawl_status[url]
        status.status = "in_progress"
        status.start_time = datetime.now().isoformat()
        status.attempt_count += 1
        
        self.logger.info(f"Processing URL: {url} (Level {status.level}, Attempt {status.attempt_count})")
        
        try:
            # Invoke Lambda
            result = self.invoke_lambda(url)
            
            # Process successful result
            if result.get('success'):
                status.status = "completed"
                status.end_time = datetime.now().isoformat()
                status.md_hash = result.get('md_hash')
                status.last_modified = result.get('last_modified')
                status.s3_key = result.get('s3_key')
                
                # Store results
                self.crawl_results[url] = result
                
                # Add extracted links for next level
                if status.level < self.config.max_levels - 1:
                    extracted_links = result.get('extracted_links', [])
                    if extracted_links:
                        self.add_urls(extracted_links, status.level + 1, url)
                        self.logger.info(f"Added {len(extracted_links)} links from {url}")
                
                self.logger.info(f"Successfully processed {url}")
                return True
                
            else:
                raise Exception(result.get('error', 'Unknown error'))
                
        except Exception as e:
            status.error = str(e)
            
            if status.attempt_count < self.config.retry_attempts:
                status.status = "pending"
                self.pending_urls.append(url)  # Re-queue for retry
                self.logger.warning(f"Retrying {url} (attempt {status.attempt_count + 1})")
            else:
                status.status = "failed"
                status.end_time = datetime.now().isoformat()
                self.logger.error(f"Failed to process {url}: {e}")
                
            return False
            
    def run_crawler(self, initial_urls: List[str]):
        """Main crawler execution loop"""
        # Apply debug limits
        if self.config.debug_mode and len(initial_urls) > self.config.debug_max_urls:
            initial_urls = initial_urls[:self.config.debug_max_urls]
            self.logger.info(f"Debug mode: limiting to {len(initial_urls)} URLs")
            
        # Initialize with starting URLs
        self.add_urls(initial_urls, level=0)
        
        self.logger.info(f"Starting crawler with {len(self.pending_urls)} URLs")
        
        futures = []
        
        try:
            while self.pending_urls or futures:
                # Start new crawls up to concurrency limit
                while (len(futures) < self.config.max_concurrency and 
                       self.pending_urls):
                    url = self.pending_urls.pop(0)
                    
                    # Skip if already processed
                    if url in self.processed_urls:
                        continue
                        
                    future = self.executor.submit(self.process_url, url)
                    futures.append((future, url))
                    
                # Wait for completions
                if futures:
                    completed_futures = []
                    for future, url in futures:
                        if future.done():
                            completed_futures.append((future, url))
                            
                    # Process completed futures
                    for future, url in completed_futures:
                        futures.remove((future, url))
                        try:
                            success = future.result()
                            if success:
                                self.processed_urls.add(url)
                        except Exception as e:
                            self.logger.error(f"Future error for {url}: {e}")
                            
                    # Save state periodically
                    if len(self.processed_urls) % 10 == 0:
                        self.save_state()
                        
                # Progress update
                total_urls = len(self.crawl_status)
                completed = len([s for s in self.crawl_status.values() if s.status == "completed"])
                failed = len([s for s in self.crawl_status.values() if s.status == "failed"])
                
                self.logger.info(f"Progress: {completed}/{total_urls} completed, "
                               f"{failed} failed, {len(futures)} active, "
                               f"{len(self.pending_urls)} pending")
                
                # Rate limiting
                time.sleep(self.config.rate_limit_delay)
                
        except KeyboardInterrupt:
            self.logger.info("Crawling interrupted by user")
        finally:
            # Wait for active crawls to complete
            for future, url in futures:
                try:
                    future.result(timeout=60)
                except Exception as e:
                    self.logger.error(f"Error waiting for {url}: {e}")
                    
            # Final state save
            self.save_state()
            
        self.logger.info("Crawling completed")
        self.print_summary()
        
    def print_summary(self):
        """Print crawling summary"""
        completed = len([s for s in self.crawl_status.values() if s.status == "completed"])
        failed = len([s for s in self.crawl_status.values() if s.status == "failed"])
        total = len(self.crawl_status)
        
        print(f"\n{'='*50}")
        print(f"CRAWLING SUMMARY")
        print(f"{'='*50}")
        print(f"Total URLs processed: {total}")
        print(f"Successfully completed: {completed}")
        print(f"Failed: {failed}")
        print(f"Success rate: {(completed/total*100):.1f}%" if total > 0 else "N/A")
        print(f"Results saved to: {self.crawl_results_file}")
        print(f"{'='*50}\n")
        
    def generate_page_slug(self, url: str) -> str:
        """Generate a readable page slug from URL"""
        import re
        from urllib.parse import urlparse
        
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
            page_name = re.sub(r'\.[^.]*
        """Download all markdown files from S3 to local structure"""
        self.logger.info("Downloading markdown files from S3...")
        
        downloaded_count = 0
        
        for url, status in self.crawl_status.items():
            if status.status == "completed" and status.s3_key:
                try:
                    # Generate page slug and filename
                    page_slug = self.generate_page_slug(url)
                    filename = f"{status.md_hash}_{page_slug}.md"
                    
                    # Create local path structure
                    parsed_url = urlparse(url)
                    domain_dir = self.local_markdown_dir / parsed_url.netloc
                    domain_dir.mkdir(exist_ok=True)
                    
                    # Set local file path with descriptive name
                    local_path = domain_dir / filename
                    
                    # Download from S3
                    self.s3_client.download_file(
                        self.config.s3_bucket,
                        status.s3_key,
                        str(local_path)
                    )
                    
                    # Create metadata file with matching name
                    metadata = {
                        'url': url,
                        'md_hash': status.md_hash,
                        'page_slug': page_slug,
                        'filename': f"{status.md_hash}_{page_slug}",
                        'last_modified': status.last_modified,
                        's3_key': status.s3_key,
                        'downloaded_at': datetime.now().isoformat()
                    }
                    
                    metadata_filename = f"{status.md_hash}_{page_slug}_metadata.json"
                    metadata_path = domain_dir / metadata_filename
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)
                        
                    downloaded_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to download {url}: {e}")
                    
        self.logger.info(f"Downloaded {downloaded_count} markdown files to {self.local_markdown_dir}")


def main():
    parser = argparse.ArgumentParser(description='Local Web Crawler Orchestrator')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--urls', type=str, help='File containing URLs to crawl')
    parser.add_argument('--url-list', nargs='*', help='Direct URL list')
    parser.add_argument('--max-levels', type=int, default=1, help='Maximum crawl levels')
    parser.add_argument('--max-concurrency', type=int, default=5, help='Maximum concurrent crawls')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--debug-max-sublinks', type=int, default=5, help='Max sublinks in debug mode')
    parser.add_argument('--debug-max-urls', type=int, default=10, help='Max URLs in debug mode')
    parser.add_argument('--download-only', action='store_true', help='Only download existing results')
    
    args = parser.parse_args()
    
    # Load configuration
    config = CrawlConfig(
        max_levels=args.max_levels,
        max_concurrency=args.max_concurrency,
        debug_mode=args.debug,
        debug_max_sublinks=args.debug_max_sublinks,
        debug_max_urls=args.debug_max_urls
    )
    
    # Load URLs
    urls = []
    if args.urls:
        with open(args.urls, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    elif args.url_list:
        urls = args.url_list
    else:
        print("Please provide URLs via --urls file or --url-list")
        return
        
    # Initialize orchestrator
    orchestrator = LocalOrchestrator(config)
    orchestrator.load_state()
    
    if args.download_only:
        orchestrator.download_markdown_files()
    else:
        # Run crawler
        orchestrator.run_crawler(urls)
        
        # Download results
        orchestrator.download_markdown_files()


if __name__ == "__main__":
    main(), '', page_name)  # Remove extension
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
        
    def download_markdown_files(self):
        """Download all markdown files from S3 to local structure"""
        self.logger.info("Downloading markdown files from S3...")
        
        downloaded_count = 0
        
        for url, status in self.crawl_status.items():
            if status.status == "completed" and status.s3_key:
                try:
                    # Create local path structure
                    parsed_url = urlparse(url)
                    domain_dir = self.local_markdown_dir / parsed_url.netloc
                    domain_dir.mkdir(exist_ok=True)
                    
                    # Generate filename
                    filename = f"{status.md_hash}.md"
                    local_path = domain_dir / filename
                    
                    # Download from S3
                    self.s3_client.download_file(
                        self.config.s3_bucket,
                        status.s3_key,
                        str(local_path)
                    )
                    
                    # Create metadata file
                    metadata = {
                        'url': url,
                        'md_hash': status.md_hash,
                        'last_modified': status.last_modified,
                        's3_key': status.s3_key,
                        'downloaded_at': datetime.now().isoformat()
                    }
                    
                    metadata_path = domain_dir / f"{status.md_hash}_metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)
                        
                    downloaded_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to download {url}: {e}")
                    
        self.logger.info(f"Downloaded {downloaded_count} markdown files to {self.local_markdown_dir}")


def main():
    parser = argparse.ArgumentParser(description='Local Web Crawler Orchestrator')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--urls', type=str, help='File containing URLs to crawl')
    parser.add_argument('--url-list', nargs='*', help='Direct URL list')
    parser.add_argument('--max-levels', type=int, default=1, help='Maximum crawl levels')
    parser.add_argument('--max-concurrency', type=int, default=5, help='Maximum concurrent crawls')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--debug-max-sublinks', type=int, default=5, help='Max sublinks in debug mode')
    parser.add_argument('--debug-max-urls', type=int, default=10, help='Max URLs in debug mode')
    parser.add_argument('--download-only', action='store_true', help='Only download existing results')
    
    args = parser.parse_args()
    
    # Load configuration
    config = CrawlConfig(
        max_levels=args.max_levels,
        max_concurrency=args.max_concurrency,
        debug_mode=args.debug,
        debug_max_sublinks=args.debug_max_sublinks,
        debug_max_urls=args.debug_max_urls
    )
    
    # Load URLs
    urls = []
    if args.urls:
        with open(args.urls, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    elif args.url_list:
        urls = args.url_list
    else:
        print("Please provide URLs via --urls file or --url-list")
        return
        
    # Initialize orchestrator
    orchestrator = LocalOrchestrator(config)
    orchestrator.load_state()
    
    if args.download_only:
        orchestrator.download_markdown_files()
    else:
        # Run crawler
        orchestrator.run_crawler(urls)
        
        # Download results
        orchestrator.download_markdown_files()


if __name__ == "__main__":
    main()