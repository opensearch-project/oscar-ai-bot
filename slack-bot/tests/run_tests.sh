#!/bin/bash

# Run all tests
cd "$(dirname "$0")/.."

# Check for required dependencies
echo "Checking for required dependencies..."
pip install pytest slack_bolt boto3

# Run tests
echo "Running tests..."
PYTHONPATH=. pytest tests/ -v