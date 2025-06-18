# Complete Test Setup and Demo Instructions

This guide provides a complete test environment to demonstrate the hybrid crawler's local-first crawling with Lambda fallback for geo-blocked content.

## 🎯 **What This Demo Shows**

✅ **Local crawling** of normal websites (fast, efficient)
✅ **Geo-block detection** using content analysis  
✅ **Lambda fallback** triggered automatically for geo-blocked sites
✅ **Local file storage** vs **S3 download** depending on method used
✅ **Multi-threaded processing** with configurable workers
✅ **Comprehensive result tracking** and analysis

## 📁 **Required Files**

You'll need these 3 files in your working directory:

1. **`hybrid_crawler.py`** - Main hybrid crawler
2. **`test_setup.py`** - Mock website servers  
3. **`test_runner.py`** - Automated test suite

Optional files:
- **`quick_test.sh`** - Simple bash test script
- **`lambda_function.py`** - For Lambda deployment (if needed)
- **`deploy_lambda.py`** - Lambda deployment script (if needed)

## 🚀 **Quick Start Demo**

### **Option 1: Automated Test Suite (Recommended)**
```bash
# Run the complete automated test
python3 test_runner.py
```

### **Option 2: Manual Step-by-Step**
```bash
# Step 1: Start mock websites
python3 test_setup.py &

# Step 2: Run crawler tests
python3 hybrid_crawler.py --urls test_urls.txt --workers 3

# Step 3: Check results
ls crawl_output/markdown/
cat crawl_output/results/crawl_summary_*.json
```

### **Option 3: One-Command Test**
```bash
# Run the bash test script
chmod +x quick_test.sh
./quick_test.sh
```

## 🌐 **Mock Website Details**

The test setup creates two local websites:

### **Normal Website (Port 8001)**
- **URL**: `http://localhost:8001/`
- **Pages**: `/`, `/about`, `/services`, `/contact`
- **Behavior**: Normal content, crawls locally
- **Expected**: Local crawling success

### **Geo-blocked Website (Port 8002)**  
- **URL**: `http://localhost:8002/`
- **Pages**: `/`, `/about`, `/premium`
- **Behavior**: Contains "your location not permitted" text
- **Expected**: Triggers Lambda fallback

## 📊 **Expected Test Results**

### **Local Crawling (localhost:8001)**
```
✅ localhost:8001/ → Local crawl → Saved locally
✅ localhost:8001/about → Local crawl → Saved locally  
✅ localhost:8001/services → Local crawl → Saved locally
✅ localhost:8001/contact → Local crawl → Saved locally
```

### **Lambda Fallback (localhost:8002)**
```
🔄 localhost:8002/ → Geo-blocked detected → Lambda fallback → S3 download
🔄 localhost:8002/about → Geo-blocked detected → Lambda fallback → S3 download
🔄 localhost:8002/premium → Geo-blocked detected → Lambda fallback → S3 download
```

## 🔧 **Environment Setup**

### **Minimum (Local Only)**
```bash
# Just for local crawling - no AWS needed
export DEEPSEEK_API_KEY="your-deepseek-api-key"  # Optional for AI analysis
python3 hybrid_crawler.py --urls test_urls.txt
```

### **Full Setup (With Lambda Fallback)**
```bash
# For complete demonstration including Lambda
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export AWS_ACCESS_KEY_ID="your-aws-access-key"
export AWS_SECRET_ACCESS_KEY="your-aws-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Deploy Lambda function first
python3 deploy_lambda.py

# Then run tests
python3 test_runner.py
```

## 📁 **Output Structure**

After running tests, you'll see:

```
crawl_output/
├── markdown/                    # Crawled content
│   ├── abc123def456.md         # Local crawl result
│   ├── def789ghi012.md         # Lambda fallback result  
│   └── ...
├── results/                     # Metadata and analysis
│   ├── abc123def456_metadata.json
│   ├── def789ghi012_metadata.json
│   └── crawl_summary_1234567890.json
└── hybrid_crawler.log          # Detailed logs

test_urls.txt                   # Generated test URLs
```

### **Sample Metadata (Local Crawl)**
```json
{
  "url": "http://localhost:8001/",
  "md_hash": "abc123def456",
  "method": "crawl4ai_local",
  "content_length": 1234,
  "extracted_links": [
    "http://localhost:8001/about",
    "http://localhost:8001/services"
  ],
  "analysis": {
    "main_topic": "Normal Website - Home",
    "content_type": "corporate",
    "summary": "Welcome page for web development services"
  },
  "s3_key": null,
  "markdown_file": "markdown/abc123def456.md"
}
```

### **Sample Metadata (Lambda Fallback)**
```json
{
  "url": "http://localhost:8002/",
  "md_hash": "def789ghi012", 
  "method": "lambda_fallback",
  "content_length": 856,
  "analysis": {
    "main_topic": "Access Restricted",
    "content_type": "error_page",
    "summary": "Geo-blocked content with location restrictions"
  },
  "s3_key": "markdown/localhost:8002/def789ghi012_20250608_143000.md",
  "markdown_file": "markdown/def789ghi012.md"
}
```

## 🧪 **Specific Test Scenarios**

### **Test 1: Verify Local Crawling**
```bash
# Should process localhost:8001 URLs locally
curl http://localhost:8001/about
# Look for this content in crawl_output/markdown/[hash].md
```

### **Test 2: Verify Geo-block Detection**
```bash
# Should detect "location not permitted" and trigger Lambda
curl http://localhost:8002/
# Should show: "Your location not permitted"
```

### **Test 3: Verify Lambda Fallback**
```bash
# Check if Lambda was triggered (requires AWS setup)
grep "Lambda fallback" hybrid_crawler.log
grep "lambda_fallback" crawl_output/results/crawl_summary_*.json
```

### **Test 4: Performance Testing**
```bash
# Test with high concurrency
python3 hybrid_crawler.py --urls test_urls.txt --workers 10
# Monitor processing speed and resource usage
```

## 🔍 **Troubleshooting**

### **Servers Won't Start**
```bash
# Check if ports are in use
netstat -tlnp | grep :8001
netstat -tlnp | grep :8002

# Kill existing processes
pkill -f "test_setup.py"
```

### **No Geo-blocking Detected**
```bash
# Manually verify geo-block content
curl http://localhost:8002/ | grep -i "location not permitted"

# Check crawler's geo-block phrases
grep "geo_block_phrases" hybrid_crawler.py
```

### **Lambda Not Triggered**
```bash
# Check AWS credentials
aws sts get-caller-identity

# Check Lambda function exists
aws lambda get-function --function-name web-crawler-analyzer

# Check crawler logs
tail -f hybrid_crawler.log
```

### **No Content Saved**
```bash
# Check permissions
ls -la crawl_output/

# Check for errors
cat hybrid_crawler.log | grep -i error

# Test with verbose output
python3 hybrid_crawler.py --urls test_urls.txt --workers 1
```

## 📈 **Performance Monitoring**

### **Real-time Monitoring**
```bash
# Monitor progress
watch -n 2 'ls crawl_output/markdown/ | wc -l'

# Monitor logs
tail -f hybrid_crawler.log

# Monitor system resources
htop  # or top
```

### **Post-test Analysis**
```bash
# View summary statistics
cat crawl_output/results/crawl_summary_*.json | jq '.crawl_session'

# Count results by method
grep -h '"method":' crawl_output/results/*_metadata.json | sort | uniq -c

# Check processing times
grep -h '"processing_time":' crawl_output/results/crawl_summary_*.json
```

## 🎯 **Success Criteria**

A successful test should show:

✅ **7 URLs processed** (4 normal + 3 geo-blocked)  
✅ **4 local successes** (localhost:8001 URLs)  
✅ **3 Lambda fallbacks** (localhost:8002 URLs, if AWS configured)  
✅ **0 failures** (all URLs should be processed)  
✅ **7 markdown files** created in output directory  
✅ **7 metadata files** with correct method attribution  
✅ **1 summary file** with accurate statistics  

## 🎉 **Demo Script**

Use this script to demonstrate the crawler:

```bash
echo "🎬 Hybrid Web Crawler Demo"
echo "=========================="

echo "1. Starting mock websites..."
python3 test_setup.py &
sleep 3

echo "2. Testing normal website (should crawl locally):"
curl -s http://localhost:8001/ | head -5

echo "3. Testing geo-blocked website (should trigger Lambda):"
curl -s http://localhost:8002/ | grep -i "location not permitted"

echo "4. Running hybrid crawler..."
python3 hybrid_crawler.py --urls test_urls.txt --workers 3

echo "5. Results:"
echo "   Markdown files: $(ls crawl_output/markdown/*.md | wc -l)"
echo "   Result files: $(ls crawl_output/results/*_metadata.json | wc -l)"

echo "6. Processing methods used:"
grep -h '"method":' crawl_output/results/*_metadata.json | sort | uniq -c

echo "Demo complete! Check crawl_output/ for full results."
```

This complete test setup demonstrates all aspects of the hybrid crawler's functionality in a controlled, reproducible environment.

---

**Ready to test? Run `python3 test_runner.py` to get started! 🚀**