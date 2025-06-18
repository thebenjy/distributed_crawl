import asyncio
import json
from webcrawleranalyzer import lambda_handler_async

async def test_local_crawl():
    # Simulate Lambda event
    event = {
        "url": "https://www.noosa.qld.gov.au",
        "config": {
            "extract_links": True,
            "max_links": 2,
            "s3_bucket": "webcrawlerresults",
            "timeout": 300,
            "analyze_content": True
        }
    }
    
    # Simulate Lambda context (can be None for local testing)
    context = None
    
    # Run the crawler
    result = await lambda_handler_async(event, context)
    
    print("Crawl Result:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(test_local_crawl())