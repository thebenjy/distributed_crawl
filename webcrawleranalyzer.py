"""
AWS Lambda function for web crawling and analysis
Uses Crawl4AI for enhanced web scraping capabilities
"""

import json
import hashlib
import logging
import tempfile
import os
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
import boto3
import requests
from bs4 import BeautifulSoup
import asyncio

# Import Crawl4AI components
try:
    from crawl4ai import AsyncWebCrawler
    from crawl4ai.extraction_strategy import LLMExtractionStrategy
    from crawl4ai.chunking_strategy import RegexChunking
except ImportError:
    # Fallback imports if Crawl4AI not available
    AsyncWebCrawler = None

# Initialize AWS clients
s3_client = boto3.client('s3')

# DeepSeek API configuration
import requests
import json
import os

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class WebCrawlerAnalyzer:
    """Main crawler and analyzer class"""
    
    def __init__(self):
        self.s3_client = s3_client
        self.deepseek_api_key = DEEPSEEK_API_KEY
        
        if not self.deepseek_api_key:
            logger.warning("DEEPSEEK_API_KEY not found in environment variables")
        
    async def crawl_url(self, url: str, config: dict) -> dict:
        """Crawl a single URL and extract content"""
        try:
            if AsyncWebCrawler:
                # Use Crawl4AI for enhanced crawling
                return await self._crawl_with_crawl4ai(url, config)
            else:
                # Fallback to basic crawling
                return await self._crawl_basic(url, config)
                
        except Exception as e:
            logger.error(f"Crawling error for {url}: {str(e)}")
            raise
            
    async def _crawl_with_crawl4ai(self, url: str, config: dict) -> dict:
        """Enhanced crawling using Crawl4AI"""
        async with AsyncWebCrawler(verbose=True) as crawler:
            # Configure crawling parameters
            crawl_config = {
                'word_count_threshold': 10,
                'css_selector': None,
                'only_text': False,
                'process_iframes': True,
                'remove_overlay_elements': True,
                'simulate_user': True,
                'override_navigator': True,
                'delay_before_return_html': 2.0,
                'wait_for': None
            }
            
            # Perform the crawl
            result = await crawler.arun(url=url, **crawl_config)
            
            if not result.success:
                raise Exception(f"Crawl failed: {result.error_message}")
                
            # Extract markdown content
            markdown_content = result.markdown
            if not markdown_content:
                markdown_content = result.cleaned_html
                
            # Extract links if requested
            extracted_links = []
            if config.get('extract_links', False):
                extracted_links = self._extract_links(result.links, url, config)
                
            # Get last modified header
            last_modified = self._get_last_modified(result.response_headers)
            
            return {
                'url': url,
                'markdown': markdown_content,
                'extracted_links': extracted_links,
                'last_modified': last_modified,
                'status_code': result.status_code,
                'content_length': len(markdown_content)
            }
            
    async def _crawl_basic(self, url: str, config: dict) -> dict:
        """Basic crawling fallback"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Convert HTML to markdown
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Extract text content
        text_content = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        markdown_content = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Extract links if requested
        extracted_links = []
        if config.get('extract_links', False):
            links = soup.find_all('a', href=True)
            link_urls = [urljoin(url, link['href']) for link in links]
            extracted_links = self._extract_links(link_urls, url, config)
            
        # Get last modified header
        last_modified = response.headers.get('Last-Modified')
        
        return {
            'url': url,
            'markdown': markdown_content,
            'extracted_links': extracted_links,
            'last_modified': last_modified,
            'status_code': response.status_code,
            'content_length': len(markdown_content)
        }
        
    def _extract_links(self, links: List[str], base_url: str, config: dict) -> List[str]:
        """Extract and filter links from crawled content"""
        if not links:
            return []
            
        # Convert relative URLs to absolute
        absolute_links = []
        base_domain = urlparse(base_url).netloc
        
        for link in links:
            if isinstance(link, dict):
                link_url = link.get('href', '')
            else:
                link_url = str(link)
                
            if not link_url or link_url.startswith('#'):
                continue
                
            # Convert to absolute URL
            absolute_url = urljoin(base_url, link_url)
            parsed = urlparse(absolute_url)
            
            # Filter out non-HTTP(S) links
            if parsed.scheme not in ['http', 'https']:
                continue
                
            # Optional: Filter to same domain only
            # if parsed.netloc != base_domain:
            #     continue
                
            absolute_links.append(absolute_url)
            
        # Remove duplicates and limit if configured
        unique_links = list(set(absolute_links))
        
        if config.get('max_links'):
            unique_links = unique_links[:config['max_links']]
            
        return unique_links
        
    def _get_last_modified(self, headers: dict) -> Optional[str]:
        """Extract last modified date from headers"""
        if not headers:
            return None
            
        # Try different header variations
        for header_name in ['Last-Modified', 'last-modified', 'LastModified']:
            if header_name in headers:
                return headers[header_name]
                
        return None
        
    def generate_md_hash(self, content: str) -> str:
        """Generate SHA-256 hash of markdown content (shortened)"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
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
            
    async def analyze_with_deepseek(self, markdown_content: str, url: str) -> dict:
        """Analyze content using DeepSeek R1 API"""
        if not self.deepseek_api_key:
            logger.warning("DeepSeek API key not available, skipping analysis")
            return {
                "main_topic": "Analysis unavailable",
                "content_type": "unknown",
                "summary": "DeepSeek API key not configured",
                "relevance_score": 0,
                "error": "API key not available"
            }
        
        try:
            # Prepare the prompt for DeepSeek R1
            prompt = f"""
            Analyze this web page content and provide a structured summary in JSON format:
            
            URL: {url}
            
            Content (truncated if necessary):
            {markdown_content[:6000]}  # Limit content for API constraints
            
            Please analyze and return a JSON object with these fields:
            1. "main_topic": The primary subject/topic of the page
            2. "key_points": Array of main points (max 5 bullet points)
            3. "content_type": Type of content (article, documentation, product page, blog post, etc.)
            4. "relevance_score": Score from 1-10 indicating content quality/relevance
            5. "summary": Brief 2-3 sentence summary
            6. "language": Detected language of the content
            7. "word_count_estimate": Estimated word count
            8. "technical_level": beginner/intermediate/advanced
            
            Return only valid JSON, no additional text.
            """
            
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-reasoner",  # Using DeepSeek R1 model
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 1500,
                "temperature": 0.1,  # Low temperature for consistent analysis
                "stream": False
            }
            
            # Make API request
            response = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            response_data = response.json()
            
            if 'choices' not in response_data or not response_data['choices']:
                raise Exception("Invalid response format from DeepSeek API")
            
            analysis_text = response_data['choices'][0]['message']['content']
            
            # Try to parse JSON response
            try:
                analysis = json.loads(analysis_text)
                
                # Validate required fields
                required_fields = ['main_topic', 'content_type', 'summary', 'relevance_score']
                for field in required_fields:
                    if field not in analysis:
                        analysis[field] = "Not available"
                
                # Ensure relevance_score is numeric
                if not isinstance(analysis.get('relevance_score'), (int, float)):
                    analysis['relevance_score'] = 5
                
                # Add metadata
                analysis['analyzed_with'] = 'deepseek-r1'
                analysis['api_model'] = 'deepseek-reasoner'
                analysis['analysis_timestamp'] = datetime.now().isoformat()
                
                logger.info(f"Successfully analyzed content with DeepSeek R1 for {url}")
                return analysis
                
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                logger.warning(f"Could not parse JSON from DeepSeek response for {url}")
                return {
                    "main_topic": "Analysis available",
                    "content_type": "unknown",
                    "summary": analysis_text[:300] + "..." if len(analysis_text) > 300 else analysis_text,
                    "relevance_score": 5,
                    "analyzed_with": "deepseek-r1",
                    "raw_response": analysis_text[:500]  # Store first 500 chars of raw response
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request failed for {url}: {str(e)}")
            return {
                "main_topic": "Analysis failed",
                "content_type": "unknown",
                "summary": "Network error during analysis",
                "relevance_score": 0,
                "error": f"Request error: {str(e)}",
                "analyzed_with": "deepseek-r1"
            }
            
        except Exception as e:
            logger.error(f"DeepSeek analysis failed for {url}: {str(e)}")
            return {
                "main_topic": "Analysis failed",
                "content_type": "unknown",
                "summary": "Analysis could not be completed",
                "relevance_score": 0,
                "error": str(e),
                "analyzed_with": "deepseek-r1"
            }


async def lambda_handler_async(event, context):
    """Async Lambda handler"""
    try:
        # Extract parameters
        url = event.get('url')
        config = event.get('config', {})
        
        if not url:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'URL parameter is required'
                })
            }
            
        logger.info(f"Processing URL: {url}")
        
        # Initialize crawler
        crawler = WebCrawlerAnalyzer()
        
        # Crawl the URL
        crawl_result = await crawler.crawl_url(url, config)
        
        # Generate hash of markdown content
        md_hash = crawler.generate_md_hash(crawl_result['markdown'])
        
        # Save to S3
        s3_key = None
        if config.get('s3_bucket'):
            s3_key = crawler.save_to_s3(
                crawl_result['markdown'],
                url,
                md_hash,
                config['s3_bucket']
            )
            
        # Analyze with DeepSeek R1 (optional)
        analysis = {}
        if config.get('analyze_content', True):
            analysis = await crawler.analyze_with_deepseek(
                crawl_result['markdown'],
                url
            )
            
        # Prepare response
        response = {
            'success': True,
            'url': url,
            'md_hash': md_hash,
            'last_modified': crawl_result.get('last_modified'),
            's3_key': s3_key,
            'content_length': crawl_result.get('content_length', 0),
            'status_code': crawl_result.get('status_code'),
            'extracted_links': crawl_result.get('extracted_links', []),
            'analysis': analysis,
            'processed_at': datetime.now().isoformat()
        }
        
        logger.info(f"Successfully processed {url}")
        
        return {
            'statusCode': 200,
            'body': response
        }
        
    except Exception as e:
        logger.error(f"Lambda execution error: {str(e)}")
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'url': event.get('url', 'unknown')
            })
        }


def lambda_handler(event, context):
    """Main Lambda handler - synchronous wrapper"""
    return asyncio.run(lambda_handler_async(event, context)), '', page_name)  # Remove extension
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
        
    def save_to_s3(self, content: str, url: str, md_hash: str, bucket: str) -> str:
        """Save markdown content to S3 with descriptive filename"""
        # Generate page slug for S3 key
        page_slug = self.generate_page_slug(url)
        
        # Generate S3 key with descriptive name
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3_key = f"markdown/{page_slug}/{md_hash}_{page_slug}_{timestamp}.md"
        
        try:
            # Upload to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/markdown',
                Metadata={
                    'original_url': url,
                    'md_hash': md_hash,
                    'page_slug': page_slug,
                    'crawled_at': datetime.now().isoformat()
                }
            )
            
            logger.info(f"Saved markdown to S3: {s3_key}")
            return s3_key
            
        except Exception as e:
            logger.error(f"Failed to save to S3: {str(e)}")
            raise
            
    async def analyze_with_deepseek(self, markdown_content: str, url: str) -> dict:
        """Analyze content using DeepSeek R1 API"""
        if not self.deepseek_api_key:
            logger.warning("DeepSeek API key not available, skipping analysis")
            return {
                "main_topic": "Analysis unavailable",
                "content_type": "unknown",
                "summary": "DeepSeek API key not configured",
                "relevance_score": 0,
                "error": "API key not available"
            }
        
        try:
            # Prepare the prompt for DeepSeek R1
            prompt = f"""
            Analyze this web page content and provide a structured summary in JSON format:
            
            URL: {url}
            
            Content (truncated if necessary):
            {markdown_content[:6000]}  # Limit content for API constraints
            
            Please analyze and return a JSON object with these fields:
            1. "main_topic": The primary subject/topic of the page
            2. "key_points": Array of main points (max 5 bullet points)
            3. "content_type": Type of content (article, documentation, product page, blog post, etc.)
            4. "relevance_score": Score from 1-10 indicating content quality/relevance
            5. "summary": Brief 2-3 sentence summary
            6. "language": Detected language of the content
            7. "word_count_estimate": Estimated word count
            8. "technical_level": beginner/intermediate/advanced
            
            Return only valid JSON, no additional text.
            """
            
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-reasoner",  # Using DeepSeek R1 model
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 1500,
                "temperature": 0.1,  # Low temperature for consistent analysis
                "stream": False
            }
            
            # Make API request
            response = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            response_data = response.json()
            
            if 'choices' not in response_data or not response_data['choices']:
                raise Exception("Invalid response format from DeepSeek API")
            
            analysis_text = response_data['choices'][0]['message']['content']
            
            # Try to parse JSON response
            try:
                analysis = json.loads(analysis_text)
                
                # Validate required fields
                required_fields = ['main_topic', 'content_type', 'summary', 'relevance_score']
                for field in required_fields:
                    if field not in analysis:
                        analysis[field] = "Not available"
                
                # Ensure relevance_score is numeric
                if not isinstance(analysis.get('relevance_score'), (int, float)):
                    analysis['relevance_score'] = 5
                
                # Add metadata
                analysis['analyzed_with'] = 'deepseek-r1'
                analysis['api_model'] = 'deepseek-reasoner'
                analysis['analysis_timestamp'] = datetime.now().isoformat()
                
                logger.info(f"Successfully analyzed content with DeepSeek R1 for {url}")
                return analysis
                
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                logger.warning(f"Could not parse JSON from DeepSeek response for {url}")
                return {
                    "main_topic": "Analysis available",
                    "content_type": "unknown",
                    "summary": analysis_text[:300] + "..." if len(analysis_text) > 300 else analysis_text,
                    "relevance_score": 5,
                    "analyzed_with": "deepseek-r1",
                    "raw_response": analysis_text[:500]  # Store first 500 chars of raw response
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request failed for {url}: {str(e)}")
            return {
                "main_topic": "Analysis failed",
                "content_type": "unknown",
                "summary": "Network error during analysis",
                "relevance_score": 0,
                "error": f"Request error: {str(e)}",
                "analyzed_with": "deepseek-r1"
            }
            
        except Exception as e:
            logger.error(f"DeepSeek analysis failed for {url}: {str(e)}")
            return {
                "main_topic": "Analysis failed",
                "content_type": "unknown",
                "summary": "Analysis could not be completed",
                "relevance_score": 0,
                "error": str(e),
                "analyzed_with": "deepseek-r1"
            }


async def lambda_handler_async(event, context):
    """Async Lambda handler"""
    try:
        # Extract parameters
        url = event.get('url')
        config = event.get('config', {})
        
        if not url:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'success': False,
                    'error': 'URL parameter is required'
                })
            }
            
        logger.info(f"Processing URL: {url}")
        
        # Initialize crawler
        crawler = WebCrawlerAnalyzer()
        
        # Crawl the URL
        crawl_result = await crawler.crawl_url(url, config)
        
        # Generate hash of markdown content
        md_hash = crawler.generate_md_hash(crawl_result['markdown'])
        
        # Save to S3
        s3_key = None
        if config.get('s3_bucket'):
            s3_key = crawler.save_to_s3(
                crawl_result['markdown'],
                url,
                md_hash,
                config['s3_bucket']
            )
            
        # Analyze with DeepSeek R1 (optional)
        analysis = {}
        if config.get('analyze_content', True):
            analysis = await crawler.analyze_with_deepseek(
                crawl_result['markdown'],
                url
            )
            
        # Prepare response
        response = {
            'success': True,
            'url': url,
            'md_hash': md_hash,
            'last_modified': crawl_result.get('last_modified'),
            's3_key': s3_key,
            'content_length': crawl_result.get('content_length', 0),
            'status_code': crawl_result.get('status_code'),
            'extracted_links': crawl_result.get('extracted_links', []),
            'analysis': analysis,
            'processed_at': datetime.now().isoformat()
        }
        
        logger.info(f"Successfully processed {url}")
        
        return {
            'statusCode': 200,
            'body': response
        }
        
    except Exception as e:
        logger.error(f"Lambda execution error: {str(e)}")
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'url': event.get('url', 'unknown')
            })
        }


def lambda_handler(event, context):
    """Main Lambda handler - synchronous wrapper"""
    return asyncio.run(lambda_handler_async(event, context))