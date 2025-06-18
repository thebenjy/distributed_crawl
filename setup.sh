#!/bin/bash

# Web Crawler Setup Script
# This script sets up the distributed web crawler with AWS Lambda

set -e

echo "🚀 Setting up Distributed Web Crawler with AWS Lambda"
echo "=================================================="

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $python_version"

if [[ $(echo "$python_version >= 3.8" | bc -l) -eq 0 ]]; then
    echo "❌ Python 3.8 or higher required"
    exit 1
fi

# Create project directory structure
echo "📁 Creating project structure..."
mkdir -p web-crawler/{src,config,data,logs}
cd web-crawler

# Create virtual environment
# echo "🐍 Creating virtual environment..."
# python3 -m venv venv
# source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip

cp ../requirements.txt ./
# cat > requirements.txt << EOF
# boto3>=1.26.0
# botocore>=1.29.0
# aiohttp>=3.8.0
# requests>=2.28.0
# beautifulsoup4>=4.11.0
# crawl4ai>=0.2.0
# lxml>=4.9.0
# html2text>=2020.1.16
# playwright>=1.30.0
# pytest>=7.0.0
# pytest-asyncio>=0.21.0
# black>=22.0.0
# flake8>=5.0.0
# EOF

pip install -r requirements.txt

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install

# Create configuration files
echo "⚙️ Creating configuration files..."

cat > config/crawler_config.json << EOF
{
  "max_levels": 2,
  "max_concurrency": 8,
  "retry_attempts": 3,
  "timeout": 900,
  "rate_limit_delay": 1.0,
  "debug_mode": false,
  "debug_max_sublinks": 5,
  "debug_max_urls": 10,
  "lambda_function_name": "web-crawler-analyzer",
  "s3_bucket": "web-crawler-results",
  "aws_region": "us-east-1",
  "analyze_content": true,
  "extract_links": true,
  "crawl4ai_config": {
    "word_count_threshold": 10,
    "process_iframes": true,
    "remove_overlay_elements": true,
    "simulate_user": true,
    "delay_before_return_html": 2.0,
    "wait_for_selector": null,
    "screenshot": false
  }
}
EOF

cat > config/debug_config.json << EOF
{
  "max_levels": 1,
  "max_concurrency": 2,
  "retry_attempts": 2,
  "timeout": 300,
  "rate_limit_delay": 2.0,
  "debug_mode": true,
  "debug_max_sublinks": 3,
  "debug_max_urls": 5,
  "lambda_function_name": "web-crawler-analyzer",
  "s3_bucket": "web-crawler-results",
  "aws_region": "us-east-1",
  "analyze_content": true,
  "extract_links": true
}
EOF

cat > config/sample_urls.txt << EOF
https://example.com
https://docs.python.org/3/
https://aws.amazon.com/lambda/
https://github.com/unclecode/crawl4ai
https://anthropic.com
EOF

# Create AWS configuration template
cat > config/aws_setup.sh << EOF
#!/bin/bash
# AWS Setup Script - Configure AWS CLI and permissions

echo "🔧 AWS Configuration Setup"
echo "=========================="

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI first:"
    echo "   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

echo "📋 Current AWS configuration:"
aws configure list

echo ""
echo "🔑 To configure AWS credentials, run:"
echo "   aws configure"
echo ""
echo "🤖 DeepSeek API Setup:"
echo "   Set your DeepSeek API key as an environment variable:"
echo "   export DEEPSEEK_API_KEY=your_deepseek_api_key_here"
echo "   Or add it to your ~/.bashrc or ~/.zshrc file"
echo ""
echo "📝 Required AWS permissions:"
echo "   - Lambda: CreateFunction, UpdateFunctionCode, InvokeFunction"
echo "   - S3: CreateBucket, PutObject, GetObject"
echo "   - IAM: CreateRole, AttachRolePolicy"
echo ""
echo "🏗️ To deploy the Lambda function, run:"
echo "   export DEEPSEEK_API_KEY=your_api_key"
echo "   python src/lambda_deployment.py"
EOF

chmod +x config/aws_setup.sh

# Create run scripts
cat > run_crawler.py << EOF
#!/usr/bin/env python3
"""
Web Crawler Runner Script
Usage examples:
  python run_crawler.py --urls config/sample_urls.txt
  python run_crawler.py --debug --url-list https://example.com
  python run_crawler.py --download-only
"""

import sys
import os
sys.path.append('src')

from local_orchestrator import main

if __name__ == "__main__":
    main()
EOF

chmod +x run_crawler.py

cat > deploy_lambda.py << EOF
#!/usr/bin/env python3
"""
Lambda Deployment Script
Usage:
  python deploy_lambda.py --function-name web-crawler-analyzer
"""

import sys
import os
sys.path.append('src')

from lambda_deployment import main

if __name__ == "__main__":
    main()
EOF

chmod +x deploy_lambda.py

# Create test script
cat > test_crawler.py << EOF
#!/usr/bin/env python3
"""
Test the crawler with debug settings
"""

import subprocess
import sys

def run_test():
    print("🧪 Running crawler test in debug mode...")
    
    cmd = [
        sys.executable, "run_crawler.py",
        "--debug",
        "--max-levels", "1",
        "--max-concurrency", "2",
        "--debug-max-urls", "3",
        "--url-list", "https://example.com", "https://httpbin.org/html"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("✅ Test completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Test failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
EOF

chmod +x test_crawler.py

# Create README
cat > README.md << EOF
# Distributed Web Crawler with AWS Lambda

A scalable web crawler that uses AWS Lambda for distributed processing and Crawl4AI for enhanced web scraping.

## Features

- 🔄 Distributed crawling using AWS Lambda
- 📊 Local orchestration and monitoring
- 🗃️ S3 storage for markdown content
- 🧠 Claude Sonnet analysis via Bedrock
- 🔄 Restart capability with state persistence
- 🐛 Debug mode for testing
- 📈 Configurable crawling levels
- 🔗 Link extraction and following

## Quick Start

1. **Setup environment:**
   \`\`\`bash
   source venv/bin/activate
   \`\`\`

2. **Configure AWS:**
   \`\`\`bash
   ./config/aws_setup.sh
   aws configure
   \`\`\`

3. **Deploy Lambda function:**
   \`\`\`bash
   python deploy_lambda.py
   \`\`\`

4. **Test the crawler:**
   \`\`\`bash
   python test_crawler.py
   \`\`\`

5. **Run production crawl:**
   \`\`\`bash
   python run_crawler.py --urls config/sample_urls.txt
   \`\`\`

## Configuration

- \`config/crawler_config.json\` - Production settings
- \`config/debug_config.json\` - Debug/test settings
- \`config/sample_urls.txt\` - Sample URLs to crawl

## Usage Examples

\`\`\`bash
# Basic crawl
python run_crawler.py --urls config/sample_urls.txt

# Debug mode (limited URLs and links)
python run_crawler.py --debug --url-list https://example.com

# Custom settings
python run_crawler.py --max-levels 3 --max-concurrency 10 --urls myurls.txt

# Download existing results only
python run_crawler.py --download-only
\`\`\`

## Output

- \`crawler_data/\` - State and results files
- \`local_markdown/\` - Downloaded markdown files
- \`crawler.log\` - Application logs

## Architecture

The system uses a local orchestrator that manages AWS Lambda functions for distributed crawling. State is maintained locally in JSON files, allowing for easy restart and monitoring.
EOF

echo ""
echo "✅ Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Configure AWS credentials: ./config/aws_setup.sh"
echo "3. Deploy Lambda function: python deploy_lambda.py"
echo "4. Test the crawler: python test_crawler.py"
echo ""
echo "📁 Project structure created in: $(pwd)"
echo "📖 See README.md for detailed usage instructions"