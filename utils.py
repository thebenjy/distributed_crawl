#!/usr/bin/env python3
"""
Utility functions for the web crawler
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import boto3
from botocore.exceptions import ClientError


class URLValidator:
    """Validate and normalize URLs"""
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is valid and accessible"""
        try:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc]) and parsed.scheme in ['http', 'https']
        except Exception:
            return False
    
    @staticmethod
    def normalize_url(url: str, base_url: str = None) -> str:
        """Normalize URL to absolute form"""
        if base_url:
            url = urljoin(base_url, url)
        
        parsed = urlparse(url)
        # Remove fragment identifier
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        return normalized
    
    @staticmethod
    def filter_urls(urls: List[str], 
                   allowed_domains: Optional[List[str]] = None,
                   blocked_extensions: Optional[List[str]] = None) -> List[str]:
        """Filter URLs based on domain and extension rules"""
        if blocked_extensions is None:
            blocked_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', 
                                '.zip', '.rar', '.exe', '.dmg', '.pkg']
        
        filtered = []
        for url in urls:
            if not URLValidator.is_valid_url(url):
                continue
                
            parsed = urlparse(url)
            
            # Check domain whitelist
            if allowed_domains and parsed.netloc not in allowed_domains:
                continue
                
            # Check blocked extensions
            if any(url.lower().endswith(ext) for ext in blocked_extensions):
                continue
                
            filtered.append(url)
        
        return list(set(filtered))  # Remove duplicates


class HashGenerator:
    """Generate various types of hashes for content"""
    
    @staticmethod
    def md5_hash(content: str) -> str:
        """Generate MD5 hash"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    @staticmethod
    def sha256_hash(content: str) -> str:
        """Generate SHA-256 hash (shortened for filenames)"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    @staticmethod
    def content_hash(content: str, algorithm: str = 'sha256') -> str:
        """Generate content hash with specified algorithm"""
        if algorithm == 'md5':
            return HashGenerator.md5_hash(content)
        elif algorithm == 'sha256':
            return HashGenerator.sha256_hash(content)
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")


class URLSlugGenerator:
    """Generate readable slugs from URLs for filenames"""
    
    @staticmethod
    def generate_page_slug(url: str) -> str:
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
    
    def upload_content(self, content: str, key: str, metadata: Dict[str, str] = None) -> bool:
        """Upload content to S3"""
        try:
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': key,
                'Body': content.encode('utf-8'),
                'ContentType': 'text/markdown'
            }
            
            if metadata:
                upload_args['Metadata'] = metadata
                
            self.s3_client.put_object(**upload_args)
            return True
        except ClientError as e:
            logging.error(f"Failed to upload to S3: {e}")
            return False
    
    def download_content(self, key: str) -> Optional[str]:
        """Download content from S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read().decode('utf-8')
        except ClientError as e:
            logging.error(f"Failed to download from S3: {e}")
            return None
    
    def list_objects(self, prefix: str = '') -> List[Dict[str, Any]]:
        """List objects in bucket with given prefix"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            return response.get('Contents', [])
        except ClientError as e:
            logging.error(f"Failed to list S3 objects: {e}")
            return []


class ContentProcessor:
    """Process and clean crawled content"""
    
    @staticmethod
    def clean_markdown(markdown: str) -> str:
        """Clean and normalize markdown content"""
        if not markdown:
            return ""
        
        # Remove excessive whitespace
        lines = markdown.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Strip whitespace but preserve indentation for code blocks
            if line.strip():
                cleaned_lines.append(line.rstrip())
            elif cleaned_lines and cleaned_lines[-1].strip():
                # Keep single empty lines between content
                cleaned_lines.append('')
        
        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)
    
    @staticmethod
    def extract_metadata(content: str, url: str) -> Dict[str, Any]:
        """Extract metadata from content"""
        word_count = len(content.split())
        char_count = len(content)
        line_count = len(content.split('\n'))
        
        # Extract title (first heading)
        title = None
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                title = line.lstrip('#').strip()
                break
        
        return {
            'url': url,
            'title': title,
            'word_count': word_count,
            'character_count': char_count,
            'line_count': line_count,
            'processed_at': datetime.now().isoformat()
        }
    
    @staticmethod
    def truncate_content(content: str, max_words: int = 4000) -> str:
        """Truncate content to specified word count"""
        words = content.split()
        if len(words) <= max_words:
            return content
        
        truncated_words = words[:max_words]
        return ' '.join(truncated_words) + '\n\n[Content truncated...]'


class ResultsManager:
    """Manage crawling results and statistics"""
    
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
    def save_results_summary(self, crawl_status: Dict, crawl_results: Dict) -> str:
        """Generate and save a comprehensive results summary"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.results_dir / f'crawl_summary_{timestamp}.json'
        
        # Calculate statistics
        total_urls = len(crawl_status)
        completed = len([s for s in crawl_status.values() if s.status == "completed"])
        failed = len([s for s in crawl_status.values() if s.status == "failed"])
        
        # Collect error statistics
        error_types = {}
        for status in crawl_status.values():
            if status.status == "failed" and status.error:
                error_type = type(status.error).__name__ if hasattr(status.error, '__name__') else str(status.error)[:50]
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Generate level statistics
        level_stats = {}
        for status in crawl_status.values():
            level = status.level
            if level not in level_stats:
                level_stats[level] = {'total': 0, 'completed': 0, 'failed': 0}
            level_stats[level]['total'] += 1
            if status.status == "completed":
                level_stats[level]['completed'] += 1
            elif status.status == "failed":
                level_stats[level]['failed'] += 1
        
        # Content statistics
        content_stats = {
            'total_content_size': 0,
            'average_content_size': 0,
            'largest_content': 0,
            'smallest_content': float('inf')
        }
        
        if crawl_results:
            sizes = []
            for result in crawl_results.values():
                size = result.get('content_length', 0)
                if size > 0:
                    sizes.append(size)
                    content_stats['total_content_size'] += size
                    content_stats['largest_content'] = max(content_stats['largest_content'], size)
                    content_stats['smallest_content'] = min(content_stats['smallest_content'], size)
            
            if sizes:
                content_stats['average_content_size'] = sum(sizes) / len(sizes)
            if content_stats['smallest_content'] == float('inf'):
                content_stats['smallest_content'] = 0
        
        summary = {
            'crawl_summary': {
                'timestamp': timestamp,
                'total_urls': total_urls,
                'completed_urls': completed,
                'failed_urls': failed,
                'success_rate': (completed / total_urls * 100) if total_urls > 0 else 0,
                'level_statistics': level_stats,
                'error_statistics': error_types,
                'content_statistics': content_stats
            },
            'detailed_results': {
                'status_by_url': {url: {
                    'status': status.status,
                    'level': status.level,
                    'attempts': status.attempt_count,
                    'error': status.error,
                    'md_hash': status.md_hash,
                    'last_modified': status.last_modified
                } for url, status in crawl_status.items()},
                'successful_crawls': {url: result for url, result in crawl_results.items()}
            }
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return str(summary_file)
    
    def export_to_csv(self, crawl_status: Dict, output_file: str = None) -> str:
        """Export results to CSV format"""
        import csv
        
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.results_dir / f'crawl_results_{timestamp}.csv'
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['url', 'status', 'level', 'attempts', 'start_time', 'end_time', 
                         'error', 'md_hash', 'last_modified', 's3_key', 'parent_url']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for url, status in crawl_status.items():
                writer.writerow({
                    'url': url,
                    'status': status.status,
                    'level': status.level,
                    'attempts': status.attempt_count,
                    'start_time': status.start_time,
                    'end_time': status.end_time,
                    'error': status.error,
                    'md_hash': status.md_hash,
                    'last_modified': status.last_modified,
                    's3_key': status.s3_key,
                    'parent_url': status.parent_url
                })
        
        return str(output_file)


class MonitoringUtils:
    """Utilities for monitoring and logging crawler progress"""
    
    @staticmethod
    def setup_detailed_logging(log_file: str = 'crawler_detailed.log', log_level: str = 'INFO'):
        """Setup detailed logging configuration"""
        log_level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        logging.basicConfig(
            level=log_level_map.get(log_level.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        # Add memory usage logging
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        logging.info(f"Initial memory usage: {memory_mb:.1f} MB")
    
    @staticmethod
    def log_progress(current: int, total: int, status_counts: Dict[str, int], start_time: datetime):
        """Log detailed progress information"""
        elapsed = datetime.now() - start_time
        rate = current / elapsed.total_seconds() if elapsed.total_seconds() > 0 else 0
        eta_seconds = (total - current) / rate if rate > 0 else 0
        eta = datetime.now() + timedelta(seconds=eta_seconds) if eta_seconds > 0 else None
        
        logging.info(
            f"Progress: {current}/{total} ({current/total*100:.1f}%) | "
            f"Completed: {status_counts.get('completed', 0)} | "
            f"Failed: {status_counts.get('failed', 0)} | "
            f"Rate: {rate:.2f} URLs/sec | "
            f"ETA: {eta.strftime('%H:%M:%S') if eta else 'Unknown'}"
        )


class ConfigManager:
    """Manage configuration files and settings"""
    
    def __init__(self, config_dir: Path = Path('config')):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        config_path = self.config_dir / config_file
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def save_config(self, config: Dict[str, Any], config_file: str):
        """Save configuration to JSON file"""
        config_path = self.config_dir / config_file
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def merge_configs(self, base_config: Dict, override_config: Dict) -> Dict:
        """Merge two configuration dictionaries"""
        merged = base_config.copy()
        
        def deep_merge(base: Dict, override: Dict):
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
        
        deep_merge(merged, override_config)
        return merged
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        required_fields = [
            'lambda_function_name', 's3_bucket', 'aws_region',
            'max_levels', 'max_concurrency', 'timeout'
        ]
        
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Validate numeric ranges
        if config.get('max_levels', 0) < 1:
            errors.append("max_levels must be at least 1")
        
        if config.get('max_concurrency', 0) < 1:
            errors.append("max_concurrency must be at least 1")
        
        if config.get('timeout', 0) < 30:
            errors.append("timeout must be at least 30 seconds")
        
        # Validate AWS region
        valid_regions = [
            'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
            'eu-west-1', 'eu-west-2', 'eu-central-1', 'ap-southeast-1',
            'ap-southeast-2', 'ap-northeast-1'
        ]
        
        if config.get('aws_region') not in valid_regions:
            errors.append(f"Invalid AWS region: {config.get('aws_region')}")
        
        return errors


# Helper functions for backward compatibility
def create_content_hash(content: str) -> str:
    """Create SHA-256 hash of content (shortened)"""
    return HashGenerator.sha256_hash(content)

def validate_url(url: str) -> bool:
    """Validate if URL is properly formatted"""
    return URLValidator.is_valid_url(url)

def clean_content(content: str) -> str:
    """Clean markdown content"""
    return ContentProcessor.clean_markdown(content)

def generate_filename_from_url(url: str, content: str, extension: str = 'md') -> str:
    """Generate descriptive filename from URL and content"""
    return URLSlugGenerator.generate_filename(url, content, extension), '', page_name)  # Remove extension
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
    
    @staticmethod
    def generate_filename(url: str, content: str, extension: str = 'md') -> str:
        """Generate complete filename with hash and slug"""
        content_hash = HashGenerator.sha256_hash(content)
        page_slug = URLSlugGenerator.generate_page_slug(url)
        return f"{content_hash}_{page_slug}.{extension}"


class S3Manager:
    """Manage S3 operations for the crawler"""
    
    def __init__(self, bucket_name: str, region: str = 'us-east-1'):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client('s3', region_name=region)
        
    def ensure_bucket_exists(self) -> bool:
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                try:
                    if self.region == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    return True
                except ClientError:
                    return False
            return False
    
    def upload_content_with_slug(self, content: str, url: str, metadata: Dict[str, str] = None) -> str:
        """Upload content to S3 with descriptive filename"""
        try:
            # Generate descriptive S3 key
            page_slug = URLSlugGenerator.generate_page_slug(url)
            content_hash = HashGenerator.sha256_hash(content)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            s3_key = f"markdown/{page_slug}/{content_hash}_{page_slug}_{timestamp}.md"
            
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
                'Body': content.encode('utf-8'),
                'ContentType': 'text/markdown'
            }
            
            # Add metadata including slug info
            if metadata:
                metadata.update({
                    'page_slug': page_slug,
                    'content_hash': content_hash
                })
                upload_args['Metadata'] = metadata
                
            self.s3_client.put_object(**upload_args)
            return s3_key
        except ClientError as e:
            logging.error(f"Failed to upload to S3: {e}")
            raise
    
    def upload_content(self, content: str, key: str, metadata: Dict[str, str] = None) -> bool:
        """Upload content to S3"""
        try:
            upload_args = {
                'Bucket': self.bucket_name,
                'Key': key,
                'Body': content.encode('utf-8'),
                'ContentType': 'text/markdown'
            }
            
            if metadata:
                upload_args['Metadata'] = metadata
                
            self.s3_client.put_object(**upload_args)
            return True
        except ClientError as e:
            logging.error(f"Failed to upload to S3: {e}")
            return False
    
    def download_content(self, key: str) -> Optional[str]:
        """Download content from S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read().decode('utf-8')
        except ClientError as e:
            logging.error(f"Failed to download from S3: {e}")
            return None
    
    def list_objects(self, prefix: str = '') -> List[Dict[str, Any]]:
        """List objects in bucket with given prefix"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            return response.get('Contents', [])
        except ClientError as e:
            logging.error(f"Failed to list S3 objects: {e}")
            return []


class ContentProcessor:
    """Process and clean crawled content"""
    
    @staticmethod
    def clean_markdown(markdown: str) -> str:
        """Clean and normalize markdown content"""
        if not markdown:
            return ""
        
        # Remove excessive whitespace
        lines = markdown.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Strip whitespace but preserve indentation for code blocks
            if line.strip():
                cleaned_lines.append(line.rstrip())
            elif cleaned_lines and cleaned_lines[-1].strip():
                # Keep single empty lines between content
                cleaned_lines.append('')
        
        # Remove trailing empty lines
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)
    
    @staticmethod
    def extract_metadata(content: str, url: str) -> Dict[str, Any]:
        """Extract metadata from content"""
        word_count = len(content.split())
        char_count = len(content)
        line_count = len(content.split('\n'))
        
        # Extract title (first heading)
        title = None
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                title = line.lstrip('#').strip()
                break
        
        return {
            'url': url,
            'title': title,
            'word_count': word_count,
            'character_count': char_count,
            'line_count': line_count,
            'processed_at': datetime.now().isoformat()
        }
    
    @staticmethod
    def truncate_content(content: str, max_words: int = 4000) -> str:
        """Truncate content to specified word count"""
        words = content.split()
        if len(words) <= max_words:
            return content
        
        truncated_words = words[:max_words]
        return ' '.join(truncated_words) + '\n\n[Content truncated...]'


class ResultsManager:
    """Manage crawling results and statistics"""
    
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
    def save_results_summary(self, crawl_status: Dict, crawl_results: Dict) -> str:
        """Generate and save a comprehensive results summary"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_file = self.results_dir / f'crawl_summary_{timestamp}.json'
        
        # Calculate statistics
        total_urls = len(crawl_status)
        completed = len([s for s in crawl_status.values() if s.status == "completed"])
        failed = len([s for s in crawl_status.values() if s.status == "failed"])
        
        # Collect error statistics
        error_types = {}
        for status in crawl_status.values():
            if status.status == "failed" and status.error:
                error_type = type(status.error).__name__ if hasattr(status.error, '__name__') else str(status.error)[:50]
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Generate level statistics
        level_stats = {}
        for status in crawl_status.values():
            level = status.level
            if level not in level_stats:
                level_stats[level] = {'total': 0, 'completed': 0, 'failed': 0}
            level_stats[level]['total'] += 1
            if status.status == "completed":
                level_stats[level]['completed'] += 1
            elif status.status == "failed":
                level_stats[level]['failed'] += 1
        
        # Content statistics
        content_stats = {
            'total_content_size': 0,
            'average_content_size': 0,
            'largest_content': 0,
            'smallest_content': float('inf')
        }
        
        if crawl_results:
            sizes = []
            for result in crawl_results.values():
                size = result.get('content_length', 0)
                if size > 0:
                    sizes.append(size)
                    content_stats['total_content_size'] += size
                    content_stats['largest_content'] = max(content_stats['largest_content'], size)
                    content_stats['smallest_content'] = min(content_stats['smallest_content'], size)
            
            if sizes:
                content_stats['average_content_size'] = sum(sizes) / len(sizes)
            if content_stats['smallest_content'] == float('inf'):
                content_stats['smallest_content'] = 0
        
        summary = {
            'crawl_summary': {
                'timestamp': timestamp,
                'total_urls': total_urls,
                'completed_urls': completed,
                'failed_urls': failed,
                'success_rate': (completed / total_urls * 100) if total_urls > 0 else 0,
                'level_statistics': level_stats,
                'error_statistics': error_types,
                'content_statistics': content_stats
            },
            'detailed_results': {
                'status_by_url': {url: {
                    'status': status.status,
                    'level': status.level,
                    'attempts': status.attempt_count,
                    'error': status.error,
                    'md_hash': status.md_hash,
                    'last_modified': status.last_modified
                } for url, status in crawl_status.items()},
                'successful_crawls': {url: result for url, result in crawl_results.items()}
            }
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return str(summary_file)
    
    def export_to_csv(self, crawl_status: Dict, output_file: str = None) -> str:
        """Export results to CSV format"""
        import csv
        
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.results_dir / f'crawl_results_{timestamp}.csv'
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['url', 'status', 'level', 'attempts', 'start_time', 'end_time', 
                         'error', 'md_hash', 'last_modified', 's3_key', 'parent_url']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for url, status in crawl_status.items():
                writer.writerow({
                    'url': url,
                    'status': status.status,
                    'level': status.level,
                    'attempts': status.attempt_count,
                    'start_time': status.start_time,
                    'end_time': status.end_time,
                    'error': status.error,
                    'md_hash': status.md_hash,
                    'last_modified': status.last_modified,
                    's3_key': status.s3_key,
                    'parent_url': status.parent_url
                })
        
        return str(output_file)


class MonitoringUtils:
    """Utilities for monitoring and logging crawler progress"""
    
    @staticmethod
    def setup_detailed_logging(log_file: str = 'crawler_detailed.log', log_level: str = 'INFO'):
        """Setup detailed logging configuration"""
        log_level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        logging.basicConfig(
            level=log_level_map.get(log_level.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        # Add memory usage logging
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        logging.info(f"Initial memory usage: {memory_mb:.1f} MB")
    
    @staticmethod
    def log_progress(current: int, total: int, status_counts: Dict[str, int], start_time: datetime):
        """Log detailed progress information"""
        elapsed = datetime.now() - start_time
        rate = current / elapsed.total_seconds() if elapsed.total_seconds() > 0 else 0
        eta_seconds = (total - current) / rate if rate > 0 else 0
        eta = datetime.now() + timedelta(seconds=eta_seconds) if eta_seconds > 0 else None
        
        logging.info(
            f"Progress: {current}/{total} ({current/total*100:.1f}%) | "
            f"Completed: {status_counts.get('completed', 0)} | "
            f"Failed: {status_counts.get('failed', 0)} | "
            f"Rate: {rate:.2f} URLs/sec | "
            f"ETA: {eta.strftime('%H:%M:%S') if eta else 'Unknown'}"
        )


class ConfigManager:
    """Manage configuration files and settings"""
    
    def __init__(self, config_dir: Path = Path('config')):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        config_path = self.config_dir / config_file
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def save_config(self, config: Dict[str, Any], config_file: str):
        """Save configuration to JSON file"""
        config_path = self.config_dir / config_file
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def merge_configs(self, base_config: Dict, override_config: Dict) -> Dict:
        """Merge two configuration dictionaries"""
        merged = base_config.copy()
        
        def deep_merge(base: Dict, override: Dict):
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
        
        deep_merge(merged, override_config)
        return merged
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        required_fields = [
            'lambda_function_name', 's3_bucket', 'aws_region',
            'max_levels', 'max_concurrency', 'timeout'
        ]
        
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")
        
        # Validate numeric ranges
        if config.get('max_levels', 0) < 1:
            errors.append("max_levels must be at least 1")
        
        if config.get('max_concurrency', 0) < 1:
            errors.append("max_concurrency must be at least 1")
        
        if config.get('timeout', 0) < 30:
            errors.append("timeout must be at least 30 seconds")
        
        # Validate AWS region
        valid_regions = [
            'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
            'eu-west-1', 'eu-west-2', 'eu-central-1', 'ap-southeast-1',
            'ap-southeast-2', 'ap-northeast-1'
        ]
        
        if config.get('aws_region') not in valid_regions:
            errors.append(f"Invalid AWS region: {config.get('aws_region')}")
        
        return errors


# Helper functions for backward compatibility
def create_content_hash(content: str) -> str:
    """Create SHA-256 hash of content"""
    return HashGenerator.sha256_hash(content)

def validate_url(url: str) -> bool:
    """Validate if URL is properly formatted"""
    return URLValidator.is_valid_url(url)

def clean_content(content: str) -> str:
    """Clean markdown content"""
    return ContentProcessor.clean_markdown(content)