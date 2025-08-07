#!/bin/bash
# Modular OSCAR Deployment
set -e

echo "🚀 Modular OSCAR Deployment"
echo "=========================="
echo ""

# Check .env
if [ ! -f ".env" ]; then
    echo "❌ .env file not found"
    exit 1
fi

echo "Choose deployment option:"
echo "1. Full deployment (infrastructure + lambdas + permissions)"
echo "2. Update lambdas only"
echo "3. Deploy infrastructure only"
echo "4. Update permissions only"
echo ""
read -p "Enter choice (1-4): " choice

case $choice in
    1)
        echo "🏗️ Full deployment..."
        ./deploy_infrastructure.sh
        ./update_lambdas.sh
        ./update_permissions.sh
        ;;
    2)
        echo "🔄 Updating lambdas..."
        ./update_lambdas.sh
        ;;
    3)
        echo "🏗️ Deploying infrastructure..."
        ./deploy_infrastructure.sh
        ;;
    4)
        echo "🔐 Updating permissions..."
        ./update_permissions.sh
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "✅ Deployment complete!"