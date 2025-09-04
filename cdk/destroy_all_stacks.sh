#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Destroy all OSCAR CDK stacks in reverse dependency order
# This script ensures clean removal of all resources

set -e

echo "🗑️  Destroying All OSCAR CDK Stacks"
echo "===================================="

# Destroy stacks in reverse dependency order
echo "🌐 Destroying API Gateway Stack..."
cdk destroy OscarApiGatewayStack --force || echo "   ⚠️  API Gateway stack not found or already destroyed"

echo "⚡ Destroying Lambda Stack..."
cdk destroy OscarLambdaStack --force || echo "   ⚠️  Lambda stack not found or already destroyed"

echo "🔐 Destroying Permissions Stack..."
cdk destroy OscarPermissionsStack --force || echo "   ⚠️  Permissions stack not found or already destroyed"

echo "📦 Destroying Secrets Stack..."
cdk destroy OscarSecretsStack --force || echo "   ⚠️  Secrets stack not found or already destroyed"

# Clean up any remaining assets
echo ""
echo "🧹 Cleaning up local assets..."
rm -rf lambda_assets || true

echo ""
echo "✅ All OSCAR stacks destroyed successfully!"
echo ""
echo "📋 Destroyed Stacks:"
echo "   🗑️  OscarApiGatewayStack"
echo "   🗑️  OscarLambdaStack"
echo "   🗑️  OscarPermissionsStack"
echo "   🗑️  OscarSecretsStack"