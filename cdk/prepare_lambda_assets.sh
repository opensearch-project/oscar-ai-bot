#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Prepare Lambda deployment assets with dependencies installed
# This script mimics the functionality of lambda_update_scripts but for CDK deployment

set -e

echo "🔄 Preparing Lambda deployment assets with dependencies..."

# Clean up any existing deployment assets
rm -rf lambda_assets
mkdir -p lambda_assets

# Function to prepare a Lambda asset
prepare_lambda_asset() {
    local source_dir=$1
    local asset_name=$2
    local handler_file=$3
    
    echo "📦 Preparing $asset_name from $source_dir..."
    
    # Create asset directory
    mkdir -p "lambda_assets/$asset_name"
    
    # Copy source code
    cp -r "$source_dir"/* "lambda_assets/$asset_name/"
    
    # Install dependencies if requirements.txt exists
    if [ -f "$source_dir/requirements.txt" ]; then
        echo "   Installing dependencies for $asset_name..."
        pip install -r "$source_dir/requirements.txt" -t "lambda_assets/$asset_name/" --upgrade --quiet
        
        # Verify critical dependencies were installed
        echo "   Verifying dependencies..."
        if [ "$asset_name" = "oscar-agent" ]; then
            # Check for slack_bolt and boto3
            if [ ! -d "lambda_assets/$asset_name/slack_bolt" ] && [ ! -d "lambda_assets/$asset_name/slack_sdk" ]; then
                echo "❌ Missing Slack dependencies for $asset_name"
                exit 1
            fi
        fi
        
        if [ ! -d "lambda_assets/$asset_name/boto3" ]; then
            echo "❌ Missing boto3 for $asset_name"
            exit 1
        fi
        
        echo "   ✅ Dependencies verified for $asset_name"
    else
        echo "   No requirements.txt found for $asset_name"
    fi
    
    # Clean up Python cache files
    find "lambda_assets/$asset_name" -name '*.pyc' -delete
    find "lambda_assets/$asset_name" -name '__pycache__' -type d -exec rm -rf {} + || true
    
    # Show package size
    local size=$(du -sh "lambda_assets/$asset_name" | cut -f1)
    echo "   ✅ $asset_name prepared (size: $size)"
}

# Prepare all Lambda assets
prepare_lambda_asset "../oscar-agent" "oscar-agent" "app.py"
prepare_lambda_asset "../jenkins" "jenkins" "lambda_function.py"  
prepare_lambda_asset "../metrics" "metrics" "lambda_function.py"

echo ""
echo "🎉 All Lambda assets prepared successfully!"
echo ""
echo "📋 Prepared Assets:"
ls -la lambda_assets/
echo ""
echo "💡 CDK will now use these pre-built assets for deployment"