#!/bin/bash
# Required for DeepSeek API
export TOGETHER_API_KEY='b6ae6dfd1f2b41e57af7ce4489d39b3612cd2c19c9032d52cbd496d757c929f3'
export DEEPSEEK_API_KEY='b6ae6dfd1f2b41e57af7ce4489d39b3612cd2c19c9032d52cbd496d757c929f3'

# Required only if using S3 storage
# export AWS_ACCESS_KEY_ID="your_aws_access_key"
# export AWS_SECRET_ACCESS_KEY="your_aws_secret_key"
export AWS_DEFAULT_REGION="us-east-2"

python run_lambda.py