#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Test script for Communication Orchestrator.

This script provides basic testing functionality for the communication
orchestrator without requiring full Slack integration.
"""

import json
import logging
from unittest.mock import Mock, MagicMock

from config import communication_config
from message_generator import MessageGenerator
from orchestrator import CommunicationOrchestrator, parse_communication_command

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_message_generation():
    """Test message generation functionality."""
    print("=== Testing Message Generation ===")
    
    # Create mock Bedrock client
    mock_generator = MessageGenerator()
    
    # Test build failure message
    context = {
        "build_name": "opensearch-main",
        "branch": "main",
        "error_summary": "Unit tests failed in security module",
        "use_ai_enhancement": False  # Disable AI for testing
    }
    
    try:
        message = mock_generator.generate_message("build_failure", context)
        print(f"✅ Build failure message generated:")
        print(f"   {message[:100]}...")
        
        # Test validation
        errors = mock_generator.validate_message_context("build_failure", context)
        print(f"✅ Validation passed: {len(errors) == 0}")
        
    except Exception as e:
        print(f"❌ Message generation failed: {e}")

def test_command_parsing():
    """Test command parsing functionality."""
    print("\n=== Testing Command Parsing ===")
    
    test_commands = [
        "@oscar /send_notification build_failure build_name=main-build branch=main",
        "@oscar /preview_message cve_check_failure component=opensearch severity=high",
        "@oscar /list_templates",
        "regular message without command"
    ]
    
    for cmd in test_commands:
        result = parse_communication_command(cmd)
        if result:
            command_type, params = result
            print(f"✅ Parsed: {cmd}")
            print(f"   Command: {command_type}")
            print(f"   Params: {params}")
        else:
            print(f"⚪ Not a command: {cmd}")

def test_configuration():
    """Test configuration loading."""
    print("\n=== Testing Configuration ===")
    
    try:
        templates = communication_config.get_available_templates()
        print(f"✅ Available templates: {templates}")
        
        # Test template retrieval
        build_template = communication_config.get_template("build_failure")
        if build_template:
            print(f"✅ Build failure template loaded")
            print(f"   Channels: {build_template.channels}")
            print(f"   Priority: {build_template.priority}")
        
        # Test channel validation
        is_allowed = communication_config.is_channel_allowed_for_template(
            "#release-engineering", "build_failure"
        )
        print(f"✅ Channel validation: {is_allowed}")
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")

def test_orchestrator_mock():
    """Test orchestrator with mock Slack client."""
    print("\n=== Testing Orchestrator (Mock) ===")
    
    # Create mock Slack client
    mock_slack_client = Mock()
    mock_slack_client.chat_postMessage.return_value = {"ts": "1234567890.123456"}
    
    # Create orchestrator
    orchestrator = CommunicationOrchestrator(mock_slack_client)
    
    try:
        # Test preview functionality
        context = {
            "build_name": "test-build",
            "branch": "main",
            "use_ai_enhancement": False
        }
        
        result = orchestrator.preview_message("build_failure", context)
        if result["success"]:
            print("✅ Message preview successful")
            print(f"   Message length: {len(result['message'])}")
            print(f"   Target channels: {result['target_channels']}")
        else:
            print(f"❌ Preview failed: {result['error']}")
        
        # Test template listing
        templates = orchestrator.list_available_templates()
        print(f"✅ Template listing: {len(templates['templates'])} templates")
        
    except Exception as e:
        print(f"❌ Orchestrator test failed: {e}")

def main():
    """Run all tests."""
    print("Communication Orchestrator Test Suite")
    print("=" * 50)
    
    test_configuration()
    test_message_generation()
    test_command_parsing()
    test_orchestrator_mock()
    
    print("\n" + "=" * 50)
    print("Test suite completed!")

if __name__ == "__main__":
    main()