#!/bin/bash

set -e

echo "🧪 Testing V2 Agents After Permission Fix"
echo "=========================================="

# Test individual agents
test_agent() {
    local agent_id=$1
    local agent_name=$2
    local test_query=$3
    
    echo "Testing $agent_name ($agent_id)..."
    echo "Query: $test_query"
    
    # Note: Replace TESTALIASID with actual alias ID if different
    local output_file="test_$(echo $agent_name | tr '[:upper:]' '[:lower:]')_result.json"
    
    aws bedrock-agent-runtime invoke-agent \
        --agent-id "$agent_id" \
        --agent-alias-id "TSTALIASID" \
        --session-id "test-$(date +%s)" \
        --input-text "$test_query" \
        --region us-east-1 \
        --output json > "$output_file" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ $agent_name: SUCCESS"
    else
        echo "❌ $agent_name: FAILED"
        cat "$output_file"
    fi
    echo ""
}

echo "📊 Testing Individual V2 Agents"
echo "==============================="

test_agent "YXSZJ659S7" "TestAnalyzer" "Show me test coverage metrics"
test_agent "0NBATJIVCH" "BuildAnalyzer" "Show me build performance metrics"
test_agent "4FCARBPEYB" "ReleaseAnalyzer" "Show me release success rates"
test_agent "BIHPD6OLO0" "DeploymentAnalyzer" "Show me deployment performance"

echo "🎯 Testing Supervisor Agent V2"
echo "=============================="

echo "Testing knowledge base query..."
aws bedrock-agent-runtime invoke-agent \
    --agent-id "NFCKXG7OIN" \
    --agent-alias-id "TSTALIASID" \
    --session-id "supervisor-test-$(date +%s)" \
    --input-text "How do I configure OpenSearch security?" \
    --region us-east-1 \
    --output json > "test_supervisor_knowledge.json" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Supervisor Knowledge Base: SUCCESS"
else
    echo "❌ Supervisor Knowledge Base: FAILED"
fi

echo ""
echo "Testing metrics routing query..."
aws bedrock-agent-runtime invoke-agent \
    --agent-id "NFCKXG7OIN" \
    --agent-alias-id "TSTALIASID" \
    --session-id "supervisor-metrics-$(date +%s)" \
    --input-text "What are the current test results?" \
    --region us-east-1 \
    --output json > "test_supervisor_metrics.json" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Supervisor Metrics Routing: SUCCESS"
else
    echo "❌ Supervisor Metrics Routing: FAILED"
    echo "Error details:"
    cat "test_supervisor_metrics.json"
fi

echo ""
echo "🎉 Testing Complete!"
echo "==================="
echo "Check the generated JSON files for detailed responses:"
echo "- test_*_result.json (individual agents)"
echo "- test_supervisor_*.json (supervisor agent)"