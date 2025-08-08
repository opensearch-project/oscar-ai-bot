#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Configuration for Communication Orchestrator.

This module provides configuration management for the communication orchestrator
feature, including channel mappings and message templates.
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class MessageTemplate:
    """Template for automated messages."""
    name: str
    description: str
    template: str
    channels: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)  # @here, @channel, or specific users
    priority: str = "normal"  # low, normal, high, urgent

@dataclass
class CommunicationConfig:
    """Configuration for communication orchestrator."""
    
    def __init__(self):
        # Default message templates for release management
        self.message_templates = {
            "build_failure": MessageTemplate(
                name="build_failure",
                description="Notify about build failures",
                template="🚨 **Build Failure Alert** 🚨\n\nA critical build has failed and requires immediate attention.\n\n**Details:**\n- Build: {build_name}\n- Branch: {branch}\n- Failure Time: {timestamp}\n- Error: {error_summary}\n\nPlease investigate and resolve this issue as soon as possible.",
                channels=["#release-engineering", "#dev-alerts"],
                mentions=["@here"],
                priority="high"
            ),
            "cve_check_failure": MessageTemplate(
                name="cve_check_failure",
                description="Notify about CVE security check failures",
                template="🔒 **Security Alert - CVE Check Failed** 🔒\n\n**Critical security vulnerabilities detected!**\n\n**Details:**\n- Component: {component}\n- CVE IDs: {cve_ids}\n- Severity: {severity}\n- Scan Time: {timestamp}\n\n**Action Required:** Please review and address these security issues immediately.",
                channels=["#security-alerts", "#release-engineering"],
                mentions=["@channel"],
                priority="urgent"
            ),
            "release_reminder": MessageTemplate(
                name="release_reminder",
                description="Remind teams about upcoming release tasks",
                template="📅 **Release Reminder** 📅\n\n**Upcoming Release: {release_version}**\n\n**Pending Tasks:**\n{task_list}\n\n**Timeline:**\n- Release Date: {release_date}\n- Days Remaining: {days_remaining}\n\nPlease ensure all tasks are completed on time.",
                channels=["#release-coordination", "#dev-team"],
                mentions=["@here"],
                priority="normal"
            ),
            "deployment_status": MessageTemplate(
                name="deployment_status",
                description="Update on deployment status",
                template="🚀 **Deployment Status Update** 🚀\n\n**Environment:** {environment}\n**Status:** {status}\n**Version:** {version}\n\n**Details:**\n{details}\n\n**Next Steps:** {next_steps}",
                channels=["#deployments", "#release-engineering"],
                mentions=["@here"],
                priority="normal"
            ),
            "test_failure": MessageTemplate(
                name="test_failure",
                description="Notify about critical test failures",
                template="🧪 **Test Failure Alert** 🧪\n\n**Critical tests are failing and blocking the release pipeline.**\n\n**Details:**\n- Test Suite: {test_suite}\n- Failed Tests: {failed_count}\n- Success Rate: {success_rate}%\n- Failure Time: {timestamp}\n\n**Failed Tests:**\n{failed_tests}\n\nPlease investigate and fix these test failures.",
                channels=["#qa-alerts", "#dev-team"],
                mentions=["@here"],
                priority="high"
            )
        }
        
        # Channel configurations
        self.channel_configs = {
            "#release-engineering": {
                "description": "Primary channel for release engineering notifications",
                "allowed_message_types": ["build_failure", "cve_check_failure", "release_reminder", "deployment_status"],
                "default_mention": "@here"
            },
            "#security-alerts": {
                "description": "Security-focused notifications",
                "allowed_message_types": ["cve_check_failure"],
                "default_mention": "@channel"
            },
            "#dev-alerts": {
                "description": "Development team alerts",
                "allowed_message_types": ["build_failure", "test_failure"],
                "default_mention": "@here"
            },
            "#qa-alerts": {
                "description": "Quality assurance alerts",
                "allowed_message_types": ["test_failure"],
                "default_mention": "@here"
            },
            "#deployments": {
                "description": "Deployment status updates",
                "allowed_message_types": ["deployment_status"],
                "default_mention": "@here"
            },
            "#release-coordination": {
                "description": "Release coordination and planning",
                "allowed_message_types": ["release_reminder", "deployment_status"],
                "default_mention": "@here"
            },
            "#dev-team": {
                "description": "General development team notifications",
                "allowed_message_types": ["release_reminder", "test_failure"],
                "default_mention": "@here"
            }
        }
    
    def get_template(self, template_name: str) -> Optional[MessageTemplate]:
        """Get a message template by name."""
        return self.message_templates.get(template_name)
    
    def get_available_templates(self) -> List[str]:
        """Get list of available template names."""
        return list(self.message_templates.keys())
    
    def get_channels_for_template(self, template_name: str) -> List[str]:
        """Get configured channels for a specific template."""
        template = self.get_template(template_name)
        return template.channels if template else []
    
    def is_channel_allowed_for_template(self, channel: str, template_name: str) -> bool:
        """Check if a channel is allowed for a specific template."""
        channel_config = self.channel_configs.get(channel, {})
        allowed_types = channel_config.get("allowed_message_types", [])
        return template_name in allowed_types

# Global configuration instance
communication_config = CommunicationConfig()