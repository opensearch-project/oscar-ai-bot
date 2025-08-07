#!/bin/bash
# Check Lambda function configuration
set -e

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

echo "🔍 Checking Lambda function configuration"

aws lambda get-function-configuration \
    --function-name oscar-supervisor-agent \
    --region "$AWS_REGION" \
    --query '{Handler: Handler, Runtime: Runtime, State: State, LastUpdateStatus: LastUpdateStatus}' \
    --output table