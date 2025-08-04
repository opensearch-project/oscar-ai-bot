#!/bin/bash

# Deploy Communication Orchestrator for OSCAR Agent
# This script helps integrate the communication orchestrator with the existing OSCAR agent

set -e

echo "🚀 Deploying Communication Orchestrator for OSCAR Agent"
echo "======================================================="

# Check if we're in the right directory
if [ ! -d "communication-orchestrator" ]; then
    echo "❌ Error: communication-orchestrator directory not found"
    echo "Please run this script from the OSCAR project root directory"
    exit 1
fi

if [ ! -d "oscar-agent" ]; then
    echo "❌ Error: oscar-agent directory not found"
    echo "Please run this script from the OSCAR project root directory"
    exit 1
fi

echo "✅ Directory structure validated"

# Run tests
echo ""
echo "🧪 Running Communication Orchestrator tests..."
cd communication-orchestrator
python test_orchestrator.py
cd ..

if [ $? -eq 0 ]; then
    echo "✅ All tests passed!"
else
    echo "❌ Tests failed. Please fix issues before deploying."
    exit 1
fi

# Check if OSCAR agent has been modified
echo ""
echo "🔍 Checking OSCAR agent integration..."

if grep -q "CommunicationOrchestrator" oscar-agent/slack_handler.py; then
    echo "✅ OSCAR agent integration detected"
else
    echo "❌ OSCAR agent integration not found"
    echo "Please ensure slack_handler.py has been updated with communication orchestrator imports"
    exit 1
fi

# Validate configuration
echo ""
echo "⚙️  Validating configuration..."

# Check if required environment variables are set
if [ -f ".env" ]; then
    echo "✅ Environment file found"
    
    # Check for required Slack tokens
    if grep -q "SLACK_BOT_TOKEN" .env && grep -q "SLACK_SIGNING_SECRET" .env; then
        echo "✅ Slack credentials configured"
    else
        echo "⚠️  Warning: Slack credentials may not be configured"
    fi
    
    # Check for AWS region
    if grep -q "AWS_REGION" .env; then
        echo "✅ AWS region configured"
    else
        echo "⚠️  Warning: AWS region not configured"
    fi
else
    echo "⚠️  Warning: .env file not found"
fi

# Create deployment summary
echo ""
echo "📋 Deployment Summary"
echo "===================="
echo "✅ Communication Orchestrator created in: communication-orchestrator/"
echo "✅ Integration added to OSCAR agent: oscar-agent/slack_handler.py"
echo "✅ Tests passing: communication-orchestrator/test_orchestrator.py"
echo ""
echo "📁 New Files Created:"
echo "   • communication-orchestrator/__init__.py"
echo "   • communication-orchestrator/config.py"
echo "   • communication-orchestrator/message_generator.py"
echo "   • communication-orchestrator/orchestrator.py"
echo "   • communication-orchestrator/requirements.txt"
echo "   • communication-orchestrator/README.md"
echo "   • communication-orchestrator/test_orchestrator.py"
echo ""
echo "🔧 Modified Files:"
echo "   • oscar-agent/slack_handler.py (added communication orchestrator integration)"
echo ""

# Usage instructions
echo "📖 Usage Instructions"
echo "===================="
echo ""
echo "The Communication Orchestrator is now integrated with your OSCAR agent."
echo "Release managers can use the following commands:"
echo ""
echo "1. Send notifications:"
echo "   @oscar /send_notification build_failure build_name=main-build branch=main"
echo ""
echo "2. Preview messages:"
echo "   @oscar /preview_message cve_check_failure component=opensearch severity=high"
echo ""
echo "3. List available templates:"
echo "   @oscar /list_templates"
echo ""
echo "📚 For detailed documentation, see: communication-orchestrator/README.md"
echo ""

# Next steps
echo "🎯 Next Steps"
echo "============="
echo "1. Deploy your updated OSCAR agent to AWS Lambda"
echo "2. Test the communication commands in your Slack workspace"
echo "3. Customize message templates in communication-orchestrator/config.py as needed"
echo "4. Configure additional channels or message types as required"
echo ""
echo "🎉 Communication Orchestrator deployment completed successfully!"