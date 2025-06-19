- Python 3.8 or higher
- AWS CLI configured with appropriate credentials
- AWS account with Lambda and S3 access
- DeepSeek API key (get from [DeepSeek Platform](https://platform.deepseek.com/))# Distributed Web Crawler with AWS Lambda

A powerful, scalable web crawler that leverages AWS Lambda for distributed processing, Crawl4AI for enhanced web scraping, and Claude Sonnet for intelligent content analysis.

## 🌟 Features

- **🔄 Distributed Processing**: Uses AWS Lambda for scalable, parallel crawling
- **🧠 AI-Powered Analysis**: Integrates DeepSeek R1 for intelligent content analysis
- **📊 Local Orchestration**: Full control and monitoring from your local machine
- **🗃️ Cloud Storage**: Automatically saves markdown content to S3 with metadata
- **🔄 Restart Capability**: Resume interrupted crawls with state persistence
- **🐛 Debug Mode**: Limited crawling for testing and development
- **📈 Multi-Level Crawling**: Configurable depth for following links
- **🔗 Smart Link Extraction**: Intelligent link discovery and filtering
- **📋 Comprehensive Logging**: Detailed progress tracking and error reporting
- **⚡ Performance Optimized**: Efficient concurrent processing with rate limiting

## 🏗️ Architecture

The system consists of three main components:

1. **Local Orchestrator** (`local_orchestrator.py`)
   - Manages the entire crawling workflow
   - Directly invokes Lambda functions via AWS SDK
   - Tracks state in local JSON files
   - Provides real-time monitoring and restart capabilities

2. **Lambda Function** (`lambda_function.py`)
   - Handles web crawling using Crawl4AI
   - Processes content and extracts links
   - Saves markdown to S3 with metadata
   - Performs DeepSeek R1 analysis for intelligent content understanding

3. **Utility Modules** (`utils.py`)
   - URL validation and filtering
   - Content processing and cleaning
   - S3 management operations
   - Hash generation and metadata handling

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- AWS CLI configured with appropriate credentials
- AWS account with Lambda, S3, and Bedrock access

### Installation

1. **Clone and setup the project:**
   ```bash
   git clone <repository-url>
   cd web-crawler
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```

3. **Configure AWS and DeepSeek:**
   ```bash
   aws configure
   export DEEPSEEK_API_KEY="your_deepseek_api_key_here"
   ```

4. **Deploy the Lambda function:**
   ```bash
   python deploy_lambda.py --function-name web-crawler-analyzer
   ```

5. **Test the installation:**
   ```bash
   python test_crawler.py
   ```

### Basic Usage

1. **Run a simple crawl:**
   ```bash
   python run_crawler.py --urls config/sample_urls.txt
   ```

2. **Debug mode (limited crawling):**
   ```bash
   python run_crawler.py --debug --url-list https://example.com
   ```

3. **Custom configuration:**
   ```bash
   python run_crawler.py --max-levels 3 --max-concurrency 10 --urls myurls.txt
   ```

4. **Download existing results only:**
   ```bash
   python run_crawler.py --download-only
   ```

## 📋 Configuration

### Main Configuration Files

- **`config/crawler_config.json`** - Production settings
- **`config/debug_config.json`** - Debug/testing settings
- **`config/sample_urls.txt`** - Sample URLs for testing

### Configuration Options

```json
{
  "max_levels": 2,                    // Crawling depth (1 = only initial URLs)
  "max_concurrency": 8,               // Parallel Lambda invocations
  "retry_attempts": 3,                // Retry failed URLs
  "timeout": 900,                     // Lambda timeout (seconds)
  "rate_limit_delay": 1.0,            // Delay between requests
  "debug_mode": false,                // Enable debug limitations
  "debug_max_sublinks": 5,            // Max links per page in debug
  "debug_max_urls": 10,               // Max URLs to process in debug
  "lambda_function_name": "web-crawler-analyzer",
  "s3_bucket": "web-crawler-results",
  "aws_region": "us-east-1",
  "analyze_content": true,             // Enable DeepSeek R1 analysis
  "ai_provider": "deepseek",           // AI provider selection
  "deepseek_config": {                 // DeepSeek R1 configuration
    "model": "deepseek-reasoner",      // Model selection
    "max_tokens": 1500,               // Response length limit
    "temperature": 0.1,               // Creativity vs consistency
    "timeout": 30                     // API timeout seconds
  }
}
```

### Debug Mode Features

- **Limited URL Processing**: Only processes first N URLs from input
- **Reduced Link Following**: Extracts limited number of links per page
- **Enhanced Logging**: More verbose output for troubleshooting
- **Faster Testing**: Shorter timeouts and smaller batches

## 🔧 Advanced Usage

### Custom URL Lists

Create a text file with one URL per line:
```
https://docs.python.org/3/
https://aws.amazon.com/lambda/
https://github.com/unclecode/crawl4ai
https://anthropic.com
```

### Command Line Options

```bash
python run_crawler.py [OPTIONS]

Options:
  --urls FILE              File containing URLs to crawl
  --url-list URL [URL...]  Direct URL list
  --max-levels N           Maximum crawl depth (default: 1)
  --max-concurrency N      Concurrent Lambda functions (default: 5)
  --debug                  Enable debug mode
  --debug-max-sublinks N   Max sublinks in debug mode (default: 5)
  --debug-max-urls N       Max URLs in debug mode (default: 10)
  --download-only          Only download existing results
  --config FILE            Custom configuration file
```

### State Management

The crawler maintains state in three JSON files:

- **`crawler_data/pending_urls.json`** - URLs waiting to be processed
- **`crawler_data/crawl_status.json`** - Status of each URL
- **`crawler_data/crawl_results.json`** - Results and metadata

To restart an interrupted crawl, simply run the crawler again with the same configuration.

## 📊 Output and Results

### Local File Structure

```
web-crawler/
├── crawler_data/           # State files
│   ├── pending_urls.json
│   ├── crawl_status.json
│   └── crawl_results.json
├── local_markdown/         # Downloaded markdown files
│   └── domain.com/
│       ├── hash1.md
│       ├── hash1_metadata.json
│       └── hash2.md
└── crawler.log            # Application logs
```

### S3 Storage Structure

```
s3://web-crawler-results/
└── markdown/
    └── domain.com/
        └── hash_timestamp.md
```

### Result Metadata

Each crawled page includes:
- **MD5/SHA-256 hash** of the content
- **Last-Modified header** from the server
- **S3 storage key** for the markdown file
- **Extracted links** for next-level crawling
- **Content Analysis** with detailed insights:
  ```json
  {
    "main_topic": "Web Development",
    "key_points": ["Point 1", "Point 2", "Point 3"],
    "content_type": "documentation",
    "relevance_score": 8,
    "summary": "Brief summary of the content",
    "language": "en",
    "technical_level": "intermediate",
    "analyzed_with": "deepseek-r1"
  }
  ```
- **Processing timestamps** and attempt counts

## 🧪 Testing

### Run All Tests
```bash
python test_crawler.py
```

### Smoke Tests (Quick Validation)
```bash
python test_crawler.py --smoke
```

### Performance Benchmarks
```bash
python test_crawler.py --benchmark
```

### Unit Tests Only
```bash
python test_crawler.py --unit --verbose
```

### Integration Tests Only
```bash
python test_crawler.py --integration
```

## 🔧 AWS Setup and Permissions

### Required AWS Services

1. **AWS Lambda** - For distributed crawling
2. **Amazon S3** - For storing markdown content
3. **IAM** - For access management

### DeepSeek API Setup

1. **Get API Key**:
   - Visit [DeepSeek Platform](https://platform.deepseek.com/)
   - Sign up and generate an API key
   - Set environment variable: `export DEEPSEEK_API_KEY="your_key"`

2. **Model Options**:
   - `deepseek-reasoner` (R1) - Advanced reasoning (recommended)
   - `deepseek-chat` - Fast general chat model
   - `deepseek-coder` - Code-optimized model

### IAM Permissions

The deployment script automatically creates necessary IAM roles and policies:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:InvokeFunction"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": [
        "arn:aws:s3:::web-crawler-results",
        "arn:aws:s3:::web-crawler-results/*"
      ]
    }
  ]
}
```

### Manual AWS Setup

If you prefer manual setup:

1. **Create S3 bucket:**
   ```bash
   aws s3 mb s3://web-crawler-results
   ```

2. **Set DeepSeek API key:**
   ```bash
   export DEEPSEEK_API_KEY="your_deepseek_api_key"
   ```

3. **Deploy Lambda function:**
   ```bash
   python deploy_lambda.py
   ```

## 📈 Performance and Scaling

### Recommended Settings

- **Development**: `max_concurrency: 2-5`
- **Production**: `max_concurrency: 10-20`
- **Large Scale**: `max_concurrency: 50+` (with appropriate rate limiting)

### Rate Limiting

Configure `rate_limit_delay` to avoid overwhelming target websites:
- **Conservative**: 2.0 seconds
- **Balanced**: 1.0 seconds
- **Aggressive**: 0.5 seconds

### Lambda Considerations

- **Memory**: 2048 MB recommended for Crawl4AI
- **Timeout**: 15 minutes maximum
- **Concurrent Executions**: Monitor AWS Lambda limits
- **Cold Starts**: First requests may be slower

## 🐛 Troubleshooting

### Common Issues

1. **AWS Credentials Not Found**
   ```bash
   aws configure
   # or
   export AWS_ACCESS_KEY_ID=your-key
   export AWS_SECRET_ACCESS_KEY=your-secret
   ```

2. **DeepSeek API Key Missing**
   ```bash
   export DEEPSEEK_API_KEY="your_deepseek_api_key"
   # or add to ~/.bashrc or ~/.zshrc
   ```

3. **Lambda Deployment Fails**
   - Check IAM permissions
   - Verify AWS region configuration
   - Ensure sufficient Lambda quotas

4. **Crawling Fails**
   - Check target website accessibility
   - Verify Lambda function logs in CloudWatch
   - Review rate limiting settings

5. **S3 Upload Errors**
   - Verify bucket exists and is accessible
   - Check S3 permissions
   - Ensure bucket name is unique

6. **DeepSeek API Errors**
   - Verify API key is correct
   - Check API rate limits and quotas
   - Monitor DeepSeek platform status
   - Review API timeout settings

### Debug Mode

Enable debug mode for troubleshooting:
```bash
python run_crawler.py --debug --max-concurrency 1 --url-list https://example.com
```

### Logging

Check logs for detailed information:
- **Application logs**: `crawler.log`
- **Lambda logs**: AWS CloudWatch
- **Debug output**: Console with `--verbose` flag

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests
python test_crawler.py --verbose

# Run linting
flake8 src/
black src/

# Run type checking
mypy src/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Crawl4AI** - Enhanced web crawling capabilities
- **AWS Lambda** - Serverless compute platform
- **DeepSeek R1** - Advanced AI reasoning and analysis
- **BeautifulSoup** - HTML parsing
- **Boto3** - AWS SDK for Python

## 📞 Support

For issues and questions:
1. Check the [troubleshooting section](#-troubleshooting)
2. Review [existing issues](../../issues)
3. Create a [new issue](../../issues/new) with detailed information

---

**Happy Crawling! 🕷️**




# Enhanced Filename Structure

The crawler now generates descriptive filenames that include both content hash and readable page slugs.

## 📁 **New Filename Format**

### **Structure:** `<hash>_<domain>_<pagename>.<extension>`

- **`<hash>`**: First 16 characters of SHA-256 hash (for uniqueness)
- **`<domain>`**: Website domain with dots replaced by underscores
- **`<pagename>`**: Page name/path converted to slug format
- **`<extension>`**: File extension (`.md` for markdown, `.json` for metadata)

## 🌐 **Example Transformations**

### **Real Website Examples:**

| URL | Generated Filename |
|-----|-------------------|
| `https://docs.python.org/3/` | `a1b2c3d4e5f6g7h8_docs_python_org_index.md` |
| `https://docs.python.org/3/library/os.html` | `f7e6d5c4b3a2g1h8_docs_python_org_os.md` |
| `https://github.com/user/repo` | `h8g7f6e5d4c3b2a1_github_com_repo.md` |
| `https://aws.amazon.com/lambda/` | `b2a1g8h7f6e5d4c3_aws_amazon_com_lambda.md` |
| `https://example.com/about-us` | `c3b2a1h8g7f6e5d4_example_com_about_us.md` |
| `https://blog.company.com/posts/2025/tech-trends` | `d4c3b2a1h8g7f6e5_blog_company_com_tech_trends.md` |

### **Test Server Examples:**

| URL | Generated Filename |
|-----|-------------------|
| `http://localhost:8001/` | `1a2b3c4d5e6f7g8h_localhost_8001_index.md` |
| `http://localhost:8001/about` | `2b3c4d5e6f7g8h1a_localhost_8001_about.md` |
| `http://localhost:8001/services` | `3c4d5e6f7g8h1a2b_localhost_8001_services.md` |
| `http://localhost:8002/premium` | `4d5e6f7g8h1a2b3c_localhost_8002_premium.md` |

## 📂 **Directory Structure**

### **Local Storage:**
```
crawl_output/
├── markdown/
│   ├── a1b2c3d4e5f6g7h8_docs_python_org_index.md
│   ├── f7e6d5c4b3a2g1h8_docs_python_org_os.md
│   ├── h8g7f6e5d4c3b2a1_github_com_repo.md
│   └── b2a1g8h7f6e5d4c3_aws_amazon_com_lambda.md
├── results/
│   ├── a1b2c3d4e5f6g7h8_docs_python_org_index_metadata.json
│   ├── f7e6d5c4b3a2g1h8_docs_python_org_os_metadata.json
│   ├── h8g7f6e5d4c3b2a1_github_com_repo_metadata.json
│   └── b2a1g8h7f6e5d4c3_aws_amazon_com_lambda_metadata.json
└── crawl_summary_1234567890.json
```

### **S3 Storage:**
```
s3://bucket/
├── markdown/
│   ├── docs_python_org_index/
│   │   └── a1b2c3d4e5f6g7h8_docs_python_org_index_20250608_143000.md
│   ├── docs_python_org_os/
│   │   └── f7e6d5c4b3a2g1h8_docs_python_org_os_20250608_143015.md
│   ├── github_com_repo/
│   │   └── h8g7f6e5d4c3b2a1_github_com_repo_20250608_143030.md
│   └── aws_amazon_com_lambda/
│       └── b2a1g8h7f6e5d4c3_aws_amazon_com_lambda_20250608_143045.md
```

## 🔧 **Slug Generation Rules**

### **Domain Processing:**
- Remove `www.` prefix
- Replace dots (`.`) with underscores (`_`)
- Remove special characters
- Keep only alphanumeric and underscores

### **Page Name Processing:**
- Use last part of URL path
- Remove file extensions (`.html`, `.php`, etc.)
- Convert special characters to underscores
- Use `index` for root pages (`/`)
- Limit to 50 characters total

### **Examples of Edge Cases:**

| URL | Domain Part | Page Part | Final Slug |
|-----|-------------|-----------|------------|
| `https://www.example.com/` | `example_com` | `index` | `example_com_index` |
| `https://api.service.co.uk/v1/users` | `api_service_co_uk` | `users` | `api_service_co_uk_users` |
| `https://site.com/page.html` | `site_com` | `page` | `site_com_page` |
| `https://blog.com/2025/01/15/post-title/` | `blog_com` | `post_title` | `blog_com_post_title` |
| `https://long-domain-name.example.org/very-long-page-name-that-exceeds-limits` | `long_domain_name_example_org` | `very_long_page_name_that_exceeds` | `long_domain_name_example_org_very_long_page_na` |

## 📋 **Metadata Structure**

### **Enhanced Metadata File:**
```json
{
  "url": "https://docs.python.org/3/",
  "md_hash": "a1b2c3d4e5f6g7h8",
  "page_slug": "docs_python_org_index",
  "filename": "a1b2c3d4e5f6g7h8_docs_python_org_index",
  "crawled_at": "2025-06-08T14:30:00.123456",
  "method": "crawl4ai_local",
  "content_length": 12543,
  "extracted_links": [
    "https://docs.python.org/3/library/",
    "https://docs.python.org/3/tutorial/"
  ],
  "analysis": {
    "main_topic": "Python 3 Documentation",
    "content_type": "documentation",
    "summary": "Official Python 3 documentation homepage",
    "relevance_score": 9,
    "key_points": [
      "Python programming language documentation",
      "Tutorial and library reference",
      "Installation and setup guides"
    ],
    "language": "en",
    "technical_level": "intermediate"
  },
  "s3_key": "markdown/docs_python_org_index/a1b2c3d4e5f6g7h8_docs_python_org_index_20250608_143000.md",
  "markdown_file": "markdown/a1b2c3d4e5f6g7h8_docs_python_org_index.md"
}
```

## 🔍 **Benefits of New Naming**

### **1. Human Readable**
- ✅ **Before**: `a1b2c3d4e5f6g7h8f9g0h1i2j3k4l5m6.md`
- ✅ **After**: `a1b2c3d4e5f6g7h8_docs_python_org_index.md`

### **2. Easy File Management**
```bash
# Find all Python documentation files
ls *_docs_python_org_*.md

# Find all index/homepage files
ls *_index.md

# Find all GitHub repository files
ls *_github_com_*.md

# Find files from specific domain
ls *_example_com_*.md
```

### **3. Organized Directory Listings**
```bash
$ ls crawl_output/markdown/
a1b2c3d4e5f6g7h8_docs_python_org_index.md
b2c3d4e5f6g7h8i9_docs_python_org_tutorial.md
c3d4e5f6g7h8i9j0_github_com_project.md
d4e5f6g7h8i9j0k1_aws_amazon_com_lambda.md
e5f6g7h8i9j0k1l2_example_com_about.md
```

### **4. Better Search and Filtering**
```bash
# Find all about pages
find . -name "*_about.md"

# Find all documentation sites
find . -name "*_docs_*"

# Find all localhost test files
find . -name "*_localhost_*"
```

## 🛠️ **Implementation Details**

### **Code Changes Made:**

1. **Hybrid Crawler** (`hybrid_crawler.py`)
   - Added `generate_page_slug()` method
   - Updated `save_local_result()` to use descriptive filenames
   - Shortened hash to 16 characters for better readability

2. **Lambda Function** (`lambda_function.py`)
   - Added `generate_page_slug()` method
   - Updated S3 key generation with page slugs
   - Enhanced S3 metadata with slug information

3. **Local Orchestrator** (`local_orchestrator.py`)
   - Updated download function to use descriptive names
   - Enhanced metadata with slug information

4. **Utils Module** (`utils.py`)
   - Added `URLSlugGenerator` class
   - Enhanced `S3Manager` with slug-aware uploads
   - Added helper functions for filename generation

### **Backward Compatibility:**
- ✅ Old hash-only files still work
- ✅ Metadata includes both old and new filename formats
- ✅ S3 keys maintain domain organization
- ✅ All existing functionality preserved

## 📊 **File Organization Examples**

### **Large Crawl Results:**
```
crawl_output/markdown/
├── 1a2b3c4d5e6f7g8h_docs_python_org_index.md
├── 2b3c4d5e6f7g8h9i_docs_python_org_tutorial.md
├── 3c4d5e6f7g8h9i0j_docs_python_org_library.md
├── 4d5e6f7g8h9i0j1k_github_com_repo1.md
├── 5e6f7g8h9i0j1k2l_github_com_repo2.md
├── 6f7g8h9i0j1k2l3m_aws_amazon_com_lambda.md
├── 7g8h9i0j1k2l3m4n_aws_amazon_com_s3.md
├── 8h9i0j1k2l3m4n5o_stackoverflow_com_question.md
└── 9i0j1k2l3m4n5o6p_reddit_com_programming.md
```

### **Test Results:**
```
test_output/markdown/
├── abc123456789def0_localhost_8001_index.md
├── def123456789abc0_localhost_8001_about.md
├── ghi123456789def0_localhost_8001_services.md
├── jkl123456789ghi0_localhost_8001_contact.md
├── mno123456789jkl0_localhost_8002_index.md
├── pqr123456789mno0_localhost_8002_about.md
└── stu123456789pqr0_localhost_8002_premium.md
```

## 🎯 **Usage Examples**

### **Finding Specific Content:**
```bash
# Find all Python docs
ls *_docs_python_org_*.md

# Find all AWS pages
ls *_aws_amazon_com_*.md

# Find all index/home pages
ls *_index.md

# Find all test server results
ls *_localhost_*.md
```

### **Organizing by Domain:**
```bash
# Group files by domain
for file in *.md; do
    domain=$(echo $file | cut -d'_' -f2-4)
    mkdir -p "by_domain/$domain"
    cp "$file" "by_domain/$domain/"
done
```

### **Content Analysis:**
```bash
# Count pages per domain
ls *.md | cut -d'_' -f2-4 | sort | uniq -c

# Find largest files
ls -la *.md | sort -k5 -nr | head -10

# Search content across all files
grep -l "specific keyword" *.md
```

This enhanced naming system makes the crawler output much more manageable and user-friendly while maintaining all the technical benefits of content hashing for deduplication and integrity checking.

---

**🎉 Now your crawled files have meaningful, searchable names that tell you exactly what they contain!**