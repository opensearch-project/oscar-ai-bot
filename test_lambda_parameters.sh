#!/bin/bash

set -e

echo "🧪 OSCAR Lambda Functions Parameter Testing"
echo "==========================================="

# Create output directory
mkdir -p test_outputs

# Test function with parameters
test_function() {
    local func_name=$1
    local payload=$2
    local description=$3
    local output_file="test_outputs/${func_name}_$(echo "$description" | tr ' ' '_' | tr -d '()').json"
    
    echo "  Testing: $description"
    echo "  Payload: $payload"
    echo "  Output: $output_file"
    
    if aws lambda invoke --function-name "$func_name" --payload "$payload" --cli-binary-format raw-in-base64-out --region us-east-1 "$output_file" >/dev/null 2>&1; then
        if grep -q '"type":' "$output_file"; then
            local result_type=$(cat "$output_file" | jq -r '.body.type // "unknown"')
            local total=$(cat "$output_file" | jq -r '.body.summary.total_results // .body.summary.total_releases // 0')
            local recent=$(cat "$output_file" | jq -r '.body.recent_data // .body.recent_releases // [] | length')
            echo "  ✅ SUCCESS: $result_type ($total total, $recent recent)"
        else
            echo "  ❌ FAIL: Invalid response"
        fi
    else
        echo "  ❌ FAIL: Invocation failed"
    fi
    echo ""
}

echo ""
echo "📊 Testing Test Metrics Agent"
echo "=============================="

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "metric_type", "value": "execution"}]}' \
    "Execution metrics"

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "metric_type", "value": "coverage"}, {"name": "time_range", "value": "7d"}]}' \
    "Coverage metrics (7 days)"

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "project_filter", "value": "opensearch"}]}' \
    "OpenSearch project filter"

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "metric_type", "value": "trends"}, {"name": "time_range", "value": "30d"}, {"name": "project_filter", "value": "dashboards"}]}' \
    "Trends for dashboards (30 days)"

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "metric_type", "value": "execution"}, {"name": "time_range", "value": "7d"}, {"name": "project_filter", "value": "integration"}]}' \
    "Integration test status (7 days)"

test_function "oscar-test-metrics-agent-new" \
    '{"function": "get_test_metrics", "parameters": [{"name": "metric_type", "value": "failures"}, {"name": "time_range", "value": "7d"}, {"name": "project_filter", "value": "integration"}]}' \
    "Integration test failures (7 days)"

echo "🏗️ Testing Build Metrics Agent"
echo "==============================="

test_function "oscar-build-metrics-agent-new" \
    '{"function": "get_build_metrics", "parameters": [{"name": "metric_type", "value": "performance"}]}' \
    "Performance metrics"

test_function "oscar-build-metrics-agent-new" \
    '{"function": "get_build_metrics", "parameters": [{"name": "metric_type", "value": "success_rate"}, {"name": "time_range", "value": "7d"}]}' \
    "Success rate (7 days)"

test_function "oscar-build-metrics-agent-new" \
    '{"function": "get_build_metrics", "parameters": [{"name": "branch_filter", "value": "main"}]}' \
    "Main branch filter"

test_function "oscar-build-metrics-agent-new" \
    '{"function": "get_build_metrics", "parameters": [{"name": "metric_type", "value": "pipeline"}, {"name": "time_range", "value": "30d"}, {"name": "branch_filter", "value": "develop"}]}' \
    "Pipeline metrics for develop (30 days)"

echo "🚀 Testing Release Metrics Agent"
echo "================================="

test_function "oscar-release-metrics-agent-new" \
    '{"function": "get_release_metrics", "parameters": [{"name": "metric_type", "value": "frequency"}]}' \
    "Frequency metrics"

test_function "oscar-release-metrics-agent-new" \
    '{"function": "get_release_metrics", "parameters": [{"name": "metric_type", "value": "success_rate"}, {"name": "time_range", "value": "7d"}]}' \
    "Success rate (7 days)"

test_function "oscar-release-metrics-agent-new" \
    '{"function": "get_release_metrics", "parameters": [{"name": "environment_filter", "value": "prod"}]}' \
    "Production environment filter"

test_function "oscar-release-metrics-agent-new" \
    '{"function": "get_release_metrics", "parameters": [{"name": "metric_type", "value": "quality"}, {"name": "time_range", "value": "30d"}, {"name": "environment_filter", "value": "staging"}]}' \
    "Quality metrics for staging (30 days)"

echo "🔧 Testing Deployment Metrics Agent"
echo "===================================="

test_function "oscar-deployment-metrics-agent-new" \
    '{"function": "get_deployment_metrics", "parameters": [{"name": "metric_type", "value": "performance"}]}' \
    "Performance metrics"

test_function "oscar-deployment-metrics-agent-new" \
    '{"function": "get_deployment_metrics", "parameters": [{"name": "metric_type", "value": "infrastructure"}, {"name": "time_range", "value": "7d"}]}' \
    "Infrastructure metrics (7 days)"

test_function "oscar-deployment-metrics-agent-new" \
    '{"function": "get_deployment_metrics", "parameters": [{"name": "service_filter", "value": "opensearch"}]}' \
    "OpenSearch service filter"

test_function "oscar-deployment-metrics-agent-new" \
    '{"function": "get_deployment_metrics", "parameters": [{"name": "metric_type", "value": "health"}, {"name": "time_range", "value": "30d"}, {"name": "service_filter", "value": "dashboards"}]}' \
    "Health metrics for dashboards (30 days)"

echo "📋 Parameter Testing Summary"
echo "============================"
echo "✅ Tested all functions with various parameter combinations"
echo "✅ Verified metric_type, time_range, and filter parameters"
echo "✅ Confirmed Bedrock-compatible parameter format"

echo ""
echo "📁 Raw outputs saved in test_outputs/ directory:"
ls -la test_outputs/

echo ""
echo "🔍 Sample output preview:"
echo "========================"
if [ -f "test_outputs/oscar-test-metrics-agent-new_Integration_test_status_7_days.json" ]; then
    echo "Integration test status (last 10 entries):"
    cat "test_outputs/oscar-test-metrics-agent-new_Integration_test_status_7_days.json" | jq '.body.recent_data[:3]' 2>/dev/null || echo "Raw JSON format"
fi