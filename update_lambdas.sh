#!/bin/bash
# Update Lambda Functions Only
set -e

echo "🔄 Updating Lambda Functions"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Update metrics agents
echo "📦 Updating metrics agents..."
./update_metrics_code_only.sh

# Update supervisor
echo "🚀 Updating supervisor..."
rm -rf supervisor-package supervisor-package.zip
mkdir supervisor-package

pip install -r oscar-agent/requirements.txt -t supervisor-package/ --quiet
cp oscar-agent/*.py supervisor-package/
find supervisor-package -name "*.pyc" -delete 2>/dev/null || true
find supervisor-package -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cd supervisor-package && zip -r ../supervisor-package.zip . -q && cd ..
rm -rf supervisor-package

cat > supervisor-env.json << EOF
{
    "Variables": {
        "OSCAR_BEDROCK_AGENT_ID": "$OSCAR_BEDROCK_AGENT_ID",
        "OSCAR_BEDROCK_AGENT_ALIAS_ID": "$OSCAR_BEDROCK_AGENT_ALIAS_ID",
        "SESSIONS_TABLE_NAME": "${SESSIONS_TABLE_NAME:-oscar-sessions-v2}",
        "CONTEXT_TABLE_NAME": "${CONTEXT_TABLE_NAME:-oscar-context}",
        "SLACK_BOT_TOKEN": "$SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET": "$SLACK_SIGNING_SECRET",
        "DEDUP_TTL": "${DEDUP_TTL:-300}",
        "SESSION_TTL": "${SESSION_TTL:-3600}",
        "CONTEXT_TTL": "${CONTEXT_TTL:-604800}",
        "MAX_CONTEXT_LENGTH": "${MAX_CONTEXT_LENGTH:-3000}",
        "CONTEXT_SUMMARY_LENGTH": "${CONTEXT_SUMMARY_LENGTH:-500}",
        "ENABLE_DM": "${ENABLE_DM:-false}",
        "AGENT_TIMEOUT": "${AGENT_TIMEOUT:-60}",
        "AGENT_MAX_RETRIES": "${AGENT_MAX_RETRIES:-2}"
    }
}
EOF

aws lambda update-function-code \
    --function-name oscar-supervisor-agent \
    --zip-file fileb://supervisor-package.zip \
    --region "$AWS_REGION" >/dev/null

aws lambda wait function-updated --function-name oscar-supervisor-agent --region "$AWS_REGION"

aws lambda update-function-configuration \
    --function-name oscar-supervisor-agent \
    --handler app.lambda_handler \
    --environment file://supervisor-env.json \
    --region "$AWS_REGION" >/dev/null

rm -f supervisor-package.zip supervisor-env.json

echo "✅ Lambda functions updated"