#!/bin/bash

# Quick Test Script for Hybrid Crawler
# Sets up mock websites and tests the crawler functionality

set -e

echo "🧪 Hybrid Crawler Quick Test"
echo "============================"

# Check if required files exist
if [ ! -f "hybrid_crawler.py" ]; then
    echo "❌ hybrid_crawler.py not found in current directory"
    exit 1
fi

if [ ! -f "test_setup.py" ]; then
    echo "❌ test_setup.py not found in current directory"
    exit 1
fi

# Check Python and install basic requirements
echo "📦 Installing required packages..."
pip3 install --quiet requests aiohttp beautifulsoup4 2>/dev/null || {
    echo "⚠️ Some packages may not have installed. Continuing anyway..."
}

# Try to install optional packages
pip3 install --quiet boto3 crawl4ai 2>/dev/null || {
    echo "⚠️ Optional packages (boto3, crawl4ai) not installed. Basic functionality will still work."
}

echo ""
echo "🔧 Environment Check"
echo "===================="

# Check environment variables
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    echo "✅ DEEPSEEK_API_KEY is set"
    ANALYSIS_FLAG=""
else
    echo "⚠️ DEEPSEEK_API_KEY not set - analysis will be disabled"
    ANALYSIS_FLAG="--no-analysis"
fi

if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "✅ AWS credentials are set - Lambda fallback available"
    LAMBDA_AVAILABLE=true
else
    echo "⚠️ AWS credentials not set - Lambda fallback disabled"
    LAMBDA_AVAILABLE=false
fi

echo ""
echo "🚀 Starting Test Servers"
echo "========================"

# Start test servers in background
echo "Starting mock websites..."
python3 test_setup.py &
SERVER_PID=$!

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Cleaning up..."
    if [ ! -z "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
    echo "✅ Cleanup complete"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Wait for servers to start
echo "⏳ Waiting for servers to start..."
sleep 3

# Test server connectivity
echo "🔍 Testing server connectivity..."
for i in {1..10}; do
    if curl -s http://localhost:8001/ > /dev/null && curl -s http://localhost:8002/ > /dev/null; then
        echo "✅ Test servers are responding"
        break
    fi
    
    if [ $i -eq 10 ]; then
        echo "❌ Test servers failed to start"
        exit 1
    fi
    
    echo "   Attempt $i/10 - waiting..."
    sleep 1
done

# Create test URLs
echo ""
echo "📝 Creating test URLs..."
cat > test_urls.txt << EOF
http://localhost:8001/
http://localhost:8001/about
http://localhost:8001/services
http://localhost:8001/contact
http://localhost:8002/
http://localhost:8002/about
http://localhost:8002/premium
EOF

echo "Created test_urls.txt with 7 test URLs"

echo ""
echo "🧪 Running Crawler Tests"
echo "========================"

# Clear any existing output
rm -rf crawl_output test_output 2>/dev/null || true

# Test 1: Basic functionality
echo ""
echo "Test 1: Basic Local Crawling"
echo "-----------------------------"
python3 hybrid_crawler.py \
    --urls test_urls.txt \
    --workers 2 \
    $ANALYSIS_FLAG \
    --output-dir test_output

# Check results
if [ -d "test_output/markdown" ]; then
    MARKDOWN_COUNT=$(ls test_output/markdown/*.md 2>/dev/null | wc -l)
    echo "✅ Created $MARKDOWN_COUNT markdown files"
else
    echo "❌ No markdown files created"
fi

if [ -d "test_output/results" ]; then
    RESULT_COUNT=$(ls test_output/results/*_metadata.json 2>/dev/null | wc -l)
    echo "✅ Created $RESULT_COUNT result files"
    
    # Check for summary file
    if ls test_output/results/crawl_summary_*.json 1> /dev/null 2>&1; then
        SUMMARY_FILE=$(ls test_output/results/crawl_summary_*.json | tail -1)
        echo "✅ Created summary file: $(basename $SUMMARY_FILE)"
        
        # Extract key stats from summary
        if command -v jq >/dev/null 2>&1; then
            LOCAL_SUCCESS=$(jq -r '.crawl_session.local_success' "$SUMMARY_FILE" 2>/dev/null || echo "unknown")
            LAMBDA_FALLBACK=$(jq -r '.crawl_session.lambda_fallback' "$SUMMARY_FILE" 2>/dev/null || echo "unknown")
            FAILURES=$(jq -r '.crawl_session.failures' "$SUMMARY_FILE" 2>/dev/null || echo "unknown")
            
            echo "📊 Crawl Statistics:"
            echo "   Local successes: $LOCAL_SUCCESS"
            echo "   Lambda fallbacks: $LAMBDA_FALLBACK"
            echo "   Failures: $FAILURES"
        else
            echo "📊 Summary created (install 'jq' for detailed stats)"
        fi
    fi
else
    echo "❌ No result files created"
fi

# Test 2: Verify geo-blocking detection
echo ""
echo "Test 2: Geo-blocking Detection"
echo "------------------------------"

# Check if any of the localhost:8002 files contain geo-blocking content
GEO_DETECTED=false
if [ -d "test_output/markdown" ]; then
    for md_file in test_output/markdown/*.md; do
        if [ -f "$md_file" ] && grep -qi "location not permitted\|geo.blocked\|not available in your region" "$md_file"; then
            echo "✅ Geo-blocking content detected in $(basename $md_file)"
            GEO_DETECTED=true
            break
        fi
    done
fi

if [ "$GEO_DETECTED" = false ]; then
    echo "⚠️ No geo-blocking content detected (this is expected if Lambda fallback isn't configured)"
fi

# Test 3: Performance test with higher concurrency
echo ""
echo "Test 3: High Concurrency Test"
echo "-----------------------------"

START_TIME=$(date +%s)
python3 hybrid_crawler.py \
    --urls test_urls.txt \
    --workers 5 \
    $ANALYSIS_FLAG \
    --output-dir crawl_output > /dev/null 2>&1
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "✅ High concurrency test completed in ${DURATION}s"

# Test 4: Manual verification
echo ""
echo "🔍 Manual Verification"
echo "======================"

echo "You can manually verify the results:"
echo ""
echo "1. Check the crawled content:"
echo "   ls test_output/markdown/"
echo "   cat test_output/markdown/[some-hash].md"
echo ""
echo "2. Check the metadata:"
echo "   ls test_output/results/"
echo "   cat test_output/results/[some-hash]_metadata.json"
echo ""
echo "3. View the summary:"
if ls test_output/results/crawl_summary_*.json 1> /dev/null 2>&1; then
    LATEST_SUMMARY=$(ls test_output/results/crawl_summary_*.json | tail -1)
    echo "   cat $LATEST_SUMMARY"
fi
echo ""
echo "4. Test the servers manually:"
echo "   curl http://localhost:8001/  # Should show normal content"
echo "   curl http://localhost:8002/  # Should show 'location not permitted'"

# Final summary
echo ""
echo "🏁 Test Summary"
echo "==============="

TOTAL_FILES=0
if [ -d "test_output/markdown" ]; then
    TOTAL_FILES=$(ls test_output/markdown/*.md 2>/dev/null | wc -l)
fi

if [ "$TOTAL_FILES" -gt 0 ]; then
    echo "✅ Basic functionality: WORKING"
    echo "   - Created $TOTAL_FILES markdown files"
    echo "   - Results saved to test_output/"
else
    echo "❌ Basic functionality: FAILED"
fi

if [ "$GEO_DETECTED" = true ]; then
    echo "✅ Geo-blocking detection: WORKING"
else
    echo "⚠️ Geo-blocking detection: NOT TESTED (Lambda not configured)"
fi

if [ "$LAMBDA_AVAILABLE" = true ]; then
    echo "✅ Lambda fallback: AVAILABLE"
else
    echo "⚠️ Lambda fallback: NOT CONFIGURED"
fi

echo ""
echo "🎯 Next Steps:"
echo ""
if [ "$LAMBDA_AVAILABLE" = false ]; then
    echo "To enable Lambda fallback:"
    echo "1. Set AWS credentials:"
    echo "   export AWS_ACCESS_KEY_ID='your-key'"
    echo "   export AWS_SECRET_ACCESS_KEY='your-secret'"
    echo "2. Deploy Lambda function:"
    echo "   python3 deploy_lambda.py"
    echo ""
fi

if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "To enable AI analysis:"
    echo "1. Get DeepSeek API key from https://platform.deepseek.com/"
    echo "2. Set environment variable:"
    echo "   export DEEPSEEK_API_KEY='your-key'"
    echo ""
fi

echo "To run with your own URLs:"
echo "1. Create a URL file:"
echo "   echo 'https://example.com' > my_urls.txt"
echo "2. Run the crawler:"
echo "   python3 hybrid_crawler.py --urls my_urls.txt"
echo ""

if [ "$TOTAL_FILES" -gt 0 ]; then
    echo "🎉 Test completed successfully!"
    echo "   Check the test_output/ directory for results"
else
    echo "❌ Test failed - check the error messages above"
    exit 1
fi