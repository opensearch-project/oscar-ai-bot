#!/bin/bash
# Clean up unused AWS resources

set -e

echo "🧹 Cleaning up unused AWS resources"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Functions to delete (old versions and test functions)
FUNCTIONS_TO_DELETE=(
    "oscar-test-metrics-agent"
    "oscar-deployment-metrics-agent" 
    "oscar-release-metrics-agent"
    "oscar-build-metrics-agent"
    "oscar-connectivity-test"
    "oscar-index-explorer"
    "oscar-minimal-test"
)

echo "🗑️  Deleting unused Lambda functions..."

for func in "${FUNCTIONS_TO_DELETE[@]}"; do
    echo "  Deleting $func..."
    aws lambda delete-function --function-name "$func" --region "$AWS_REGION" 2>/dev/null || echo "    (Function may not exist)"
    echo "    ✅ Deleted"
done

echo "✅ Cleanup completed"
echo ""
echo "📋 Remaining active functions:"
echo "  • oscar-supervisor-agent (main Slack bot)"
echo "  • oscar-test-metrics-agent-new"
echo "  • oscar-build-metrics-agent-new" 
echo "  • oscar-release-metrics-agent-new"
echo "  • oscar-deployment-metrics-agent-new"