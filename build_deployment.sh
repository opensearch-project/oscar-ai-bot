#!/bin/bash

# Build deployment package for OSCAR Agent
# This script creates a deployment package with dependencies when needed

set -e

echo "📦 Building OSCAR Agent deployment package..."

# Check if we need to rebuild
DEPLOY_DIR="oscar-agent-deploy"
SOURCE_DIR="oscar-agent"

# Remove old deployment directory if it exists
if [ -d "$DEPLOY_DIR" ]; then
    echo "🧹 Cleaning up old deployment package..."
    rm -rf "$DEPLOY_DIR"
fi

# Create new deployment directory
mkdir -p "$DEPLOY_DIR"

# Copy source files
echo "📁 Copying source files..."
cp "$SOURCE_DIR"/*.py "$DEPLOY_DIR/"

# Install dependencies
echo "📦 Installing Python dependencies..."
cd "$DEPLOY_DIR"

# Install dependencies to the deployment directory
pip install -r "../$SOURCE_DIR/requirements.txt" -t .

# Remove unnecessary files to reduce package size
echo "🧹 Cleaning up unnecessary files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

cd ..

echo "✅ Deployment package created successfully!"
echo "📊 Package size: $(du -sh $DEPLOY_DIR | cut -f1)"