#!/bin/bash

echo "🧪 Quick V2 Agent Test"
echo "====================="

# Test one agent with timeout
echo "Testing TestAnalyzer directly..."
timeout 30s aws bedrock-agent-runtime invoke-agent \
    --agent-id "YXSZJ659S7" \
    --agent-alias-id "TSTALIASID" \
    --session-id "quicktest-$(date +%s)" \
    --input-text "Show test metrics" \
    --region us-east-1 \
    test_quick.json

if [ $? -eq 0 ]; then
    echo "✅ TestAnalyzer: SUCCESS"
    echo "Response preview:"
    head -20 test_quick.json
else
    echo "❌ TestAnalyzer: FAILED or TIMEOUT"
    if [ -f test_quick.json ]; then
        echo "Error details:"
        cat test_quick.json
    fi
fi

echo ""
echo "Now testing supervisor agent with same query that failed before..."
timeout 30s aws bedrock-agent-runtime invoke-agent \
    --agent-id "NFCKXG7OIN" \
    --agent-alias-id "TSTALIASID" \
    --session-id "supervisor-$(date +%s)" \
    --input-text "what are the current test results?" \
    --region us-east-1 \
    test_supervisor.json

if [ $? -eq 0 ]; then
    echo "✅ Supervisor: SUCCESS"
    echo "Response preview:"
    head -20 test_supervisor.json
else
    echo "❌ Supervisor: FAILED or TIMEOUT"
    if [ -f test_supervisor.json ]; then
        echo "Error details:"
        cat test_supervisor.json
    fi
fi