#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Cleanup old communication orchestrator system
# Run this after successfully deploying the new integrated system

set -e

echo "🧹 Cleaning up old communication orchestrator system..."

# Backup the old system first
if [ -d "communication-orchestrator" ]; then
    echo "📦 Creating backup of old system..."
    cp -r communication-orchestrator/ communication-orchestrator-backup-$(date +%Y%m%d-%H%M%S)/
    echo "✅ Backup created"
fi

# Remove old communication orchestrator directory
if [ -d "communication-orchestrator" ]; then
    echo "🗑️  Removing old communication-orchestrator directory..."
    rm -rf communication-orchestrator/
    echo "✅ Old directory removed"
fi

# Remove old deployment script
if [ -f "deploy_communication_orchestrator.sh" ]; then
    echo "🗑️  Removing old deployment script..."
    mv deploy_communication_orchestrator.sh deploy_communication_orchestrator.sh.old
    echo "✅ Old deployment script renamed to .old"
fi

echo ""
echo "🎉 Cleanup completed!"
echo ""
echo "📋 What was cleaned up:"
echo "   • communication-orchestrator/ directory (backed up)"
echo "   • deploy_communication_orchestrator.sh (renamed to .old)"
echo ""
echo "📦 Backup location:"
echo "   • communication-orchestrator-backup-* directory"
echo ""
echo "✅ New system files:"
echo "   • oscar-agent/communication_handler.py"
echo "   • deploy_communication_handler.sh"
echo "   • docs/COMMUNICATION_ORCHESTRATION_AGENT_CONFIG.md"
echo "   • DEPLOY_COMMUNICATION_ORCHESTRATION.md"
echo ""
echo "🚀 The new integrated communication orchestration system is ready!"