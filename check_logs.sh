#!/bin/bash
# Check CloudWatch logs for errors
set -e

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

echo "🔍 Checking CloudWatch logs for oscar-supervisor-agent"
echo "Recent log entries:"

aws logs tail /aws/lambda/oscar-supervisor-agent \
    --region "$AWS_REGION" \
    --since 5m \
    --format short