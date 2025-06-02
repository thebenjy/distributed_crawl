I'll update the architecture design to meet your requirements for a distributed crawler that runs locally, with local Lambda invocation, local monitoring, status tracking, and restart capabilities.

# Streamlined Web Crawling and Analysis Architecture with AWS Lambda and Local Orchestration

## Architecture Overview
This revised architecture uses a local orchestrator to manage AWS Lambda functions for distributed crawling and analysis, eliminating dependencies on SQS and DynamoDB:

1. **Local Orchestrator**
   - Python-based application running on the user's machine
   - Directly invokes Lambda functions via AWS SDK
   - Tracks and manages the entire crawling pipeline locally
   - Stores all state and results in local JSON files

2. **Combined Crawler-Analyzer Lambda**
   - Single Lambda function that handles both web crawling and Claude Sonnet analysis
   - Processes one URL completely before returning results
   - Invoked directly by the local orchestrator (no SQS)

3. **Storage Layer**
   - S3 buckets for backup storage (optional)
   - Local JSON files for primary state management and results storage
   - Lambda temp storage for processing during execution

4. **Integration Services**
   - AWS SDK for direct Lambda invocation
   - IAM roles for secure access to Lambda and S3

## Component Details

### Local Orchestrator
- Accepts a list of URLs to process from a configuration file
- Maintains a queue of URLs to crawl in a local JSON file (`pending_urls.json`)
- Directly invokes Lambda functions via AWS SDK's Lambda client
- Tracks processing status in a local JSON file (`crawl_status.json`)
- Saves results locally in a structured JSON format (`crawl_results.json`)
- Implements a configurable concurrency limit to control Lambda invocations
- Provides real-time status updates in the console
- Includes restart capability by persisting and loading state from JSON files

### Combined Crawler-Analyzer Lambda
- Receives a URL from the local orchestrator via direct invocation
- Performs the complete processing pipeline for each URL:
  1. Downloads webpage content
  2. Converts HTML to markdown using libraries like html2text
  3. Temporarily stores markdown in Lambda's local storage
  4. Processes the markdown using Amazon Bedrock Claude Sonnet model
  5. Returns both the markdown and analysis results to the local orchestrator
- Implements robust error handling and retry logic

### Workflow Coordination
- Local orchestrator manages the entire workflow
- Status tracking via local JSON files
- Configurable throttling to avoid overwhelming target websites
- CloudWatch for Lambda execution monitoring (optional)

## Data Flow

1. Local orchestrator loads or initializes the URL queue from `pending_urls.json`
2. Orchestrator loads existing status from `crawl_status.json` (or creates if first run)
3. For each available concurrency slot:
   - Orchestrator pops a URL from the pending queue
   - Updates status to "in_progress" in `crawl_status.json`
   - Directly invokes a Lambda function with the URL as parameter
4. Each Lambda instance:
   - Receives the URL in the invocation payload
   - Downloads and processes the webpage
   - Returns results directly to the orchestrator
5. Upon Lambda completion:
   - Orchestrator updates status to "completed" or "failed" in `crawl_status.json`
   - Saves results to `crawl_results.json`
   - Extracts new URLs from the page (if configured) and adds to pending queue
   - Launches a new Lambda for the next URL in the queue
6. Process continues until queue is empty or orchestrator is stopped
7. If orchestrator is stopped, state is preserved in JSON files for restart

## Restart Capability

- All state is stored in local JSON files:
  - `pending_urls.json`: Queue of URLs pending processing
  - `crawl_status.json`: Status of each URL (pending, in_progress, completed, failed)
  - `crawl_results.json`: Results of completed crawls
- When the orchestrator starts, it:
  1. Loads the existing state from these files
  2. Resets any "in_progress" URLs to "pending" (handling interrupted processing)
  3. Continues processing from where it left off
  4. Periodically saves state to allow for clean shutdowns

## Local Status Tracking

- `crawl_status.json` maintains a comprehensive record of all URLs:
  ```json
  {
    "https://example.com": {
      "status": "completed",
      "start_time": "2025-06-02T14:30:00",
      "end_time": "2025-06-02T14:30:45",
      "attempt_count": 1,
      "error": null
    },
    "https://another-site.com": {
      "status": "failed",
      "start_time": "2025-06-02T14:31:00",
      "end_time": "2025-06-02T14:31:23",
      "attempt_count": 3,
      "error": "Connection timeout"
    }
  }
  ```

- Real-time console output shows:
  - URLs currently being processed
  - Completion percentage
  - Error counts
  - Concurrency utilization

## Key Considerations

- **AWS SDK Configuration**: Ensure proper AWS credentials and region settings for local Lambda invocation
- **Memory Configuration**: Lambda functions need sufficient memory (1-2GB minimum)
- **Execution Time**: Configure appropriate timeout values (up to 15 minutes)
- **Concurrency Management**: Local throttling to prevent overwhelming target websites
- **Error Handling**: Robust error tracking with configurable retry logic
- **Network Reliability**: Handle network interruptions between local machine and AWS
- **Security**: Use least-privilege IAM roles with permissions for web access, S3, and Bedrock
- **Rate Limiting**: Implement adaptive rate limiting based on target website response
- **Persistence**: Frequent state saves to prevent data loss if orchestrator crashes

## Benefits of This Approach

- **Local Control**: Full visibility and control of the crawling process
- **No External Dependencies**: Eliminates SQS and DynamoDB requirements
- **Simplified Restart**: Easy restart capability through local state files
- **Cost Optimization**: Pay only for Lambda execution time
- **Flexible Scaling**: Dynamically adjust concurrency based on available resources
- **Real-time Monitoring**: Immediate visibility into crawler status
- **Offline Capability**: Can run with intermittent connectivity to AWS

This architecture provides a robust locally-orchestrated distributed crawler that leverages AWS Lambda for processing power while maintaining full local control over the crawling process.