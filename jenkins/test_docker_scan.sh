#!/bin/bash

# Quick Docker Scan Test
# Usage: ./test_docker_scan.sh [image_name]
# Example: ./test_docker_scan.sh alpine:3.19

IMAGE_NAME=${1:-"alpine:3.19"}

echo "🐳 Testing Docker scan for: $IMAGE_NAME"
echo "================================================"

aws lambda invoke \
    --function-name oscar-jenkins-agent \
    --region us-east-1 \
    --payload "{\"function\":\"docker_scan\",\"parameters\":[{\"name\":\"image_name\",\"value\":\"$IMAGE_NAME\"}]}" \
    --cli-binary-format raw-in-base64-out \
    response.json

echo ""
echo "📋 Response:"
cat response.json | jq '.'

echo ""
echo "📋 Parsed body:"
cat response.json | jq -r '.body' | jq '.'

# Clean up
rm response.json

echo ""
echo "✅ Test completed!"