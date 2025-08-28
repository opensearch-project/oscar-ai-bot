#!/usr/bin/env python3
"""
Test utilities for agent configuration extraction and validation.
Provides comprehensive testing of configuration utilities including extraction,
validation, and schema compliance.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from agent_config_builder import AgentConfig, ActionGroupConfig, KnowledgeBaseConfig, AgentConfigBuilder
from agent_config_validator import AgentConfigValidator, ValidationSeverity
from agent_config_extractor import AgentConfigExtractor, ExtractionResult


class TestAgentConfigBuilder(unittest.TestCase):
    """Test cases for AgentConfigBuilder."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.builder = AgentConfigBuilder(configs_dir=self.temp_dir)
        
        # Sample configuration data
        self.sample_config = {
            "agent_name": "test-agent",
            "description": "Test agent description",
            "instructions": "You are a test agent.",
            "foundation_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "agent_id": "TESTID1234",
            "primary_alias_id": "ALIAS12345",
            "action_groups": [
                {
                    "name": "test-action",
                    "description": "Test action group",
                    "lambda_function_arn": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
                    "api_schema": {
                        "openAPIVersion": "3.0.0",
                        "info": {"title": "Test API", "version": "1.0.0"},
                        "paths": {"/test": {"get": {"description": "Test endpoint", "parameters": {}}}}
                    }
                }
            ],
            "knowledge_bases": [
                {
                    "knowledge_base_id": "KB12345678",
                    "knowledge_base_state": "ENABLED"
                }
            ],
            "tags": {"Environment": "Test"}
        }
    
    def test_build_agent_config(self):
        """Test building agent configuration from dictionary."""
        agent_config = self.builder._build_agent_config(self.sample_config)
        
        self.assertEqual(agent_config.agent_name, "test-agent")
        self.assertEqual(agent_config.description, "Test agent description")
        self.assertEqual(len(agent_config.action_groups), 1)
        self.assertEqual(len(agent_config.knowledge_bases), 1)
        self.assertEqual(agent_config.tags["Environment"], "Test")
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration files."""
        agent_config = self.builder._build_agent_config(self.sample_config)
        
        # Save configuration
        self.builder.save_agent_config(agent_config, "test-config.json")
        
        # Load configuration
        loaded_config = self.builder.load_agent_config("test-config.json")
        
        self.assertEqual(loaded_config.agent_name, agent_config.agent_name)
        self.assertEqual(loaded_config.description, agent_config.description)
        self.assertEqual(len(loaded_config.action_groups), len(agent_config.action_groups))
    
    def test_validate_agent_config(self):
        """Test agent configuration validation."""
        agent_config = self.builder._build_agent_config(self.sample_config)
        
        # Should be valid
        self.assertTrue(self.builder.validate_agent_config(agent_config))
        
        # Test invalid configuration
        invalid_config = AgentConfig(
            agent_name="",  # Empty name should be invalid
            description="Test",
            instructions="Test",
            foundation_model="invalid-model"
        )
        
        with self.assertRaises(ValueError):
            self.builder.validate_agent_config(invalid_config)


class TestAgentConfigValidator(unittest.TestCase):
    """Test cases for AgentConfigValidator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = AgentConfigValidator()
        
        # Valid configuration
        self.valid_config = AgentConfig(
            agent_name="test-agent",
            description="Test agent description",
            instructions="You are a test agent.",
            foundation_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            agent_id="TESTID1234",
            primary_alias_id="ALIAS12345",
            action_groups=[
                ActionGroupConfig(
                    name="test-action",
                    description="Test action group",
                    lambda_function_arn="arn:aws:lambda:us-east-1:123456789012:function:test-function",
                    api_schema={
                        "openAPIVersion": "3.0.0",
                        "info": {"title": "Test API", "version": "1.0.0"},
                        "paths": {"/test": {"get": {"description": "Test endpoint", "parameters": {}}}}
                    }
                )
            ],
            knowledge_bases=[
                KnowledgeBaseConfig(
                    knowledge_base_id="KB12345678",
                    knowledge_base_state="ENABLED"
                )
            ]
        )
    
    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        result = self.validator.validate_agent_config(self.valid_config)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
    
    def test_validate_invalid_agent_name(self):
        """Test validation with invalid agent name."""
        invalid_config = AgentConfig(
            agent_name="",  # Empty name
            description="Test",
            instructions="Test",
            foundation_model="anthropic.claude-3-5-sonnet-20241022-v2:0"
        )
        
        result = self.validator.validate_agent_config(invalid_config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Agent name is required" in str(error) for error in result.errors))
    
    def test_validate_invalid_foundation_model(self):
        """Test validation with invalid foundation model."""
        invalid_config = AgentConfig(
            agent_name="test-agent",
            description="Test",
            instructions="Test",
            foundation_model="invalid-model"
        )
        
        result = self.validator.validate_agent_config(invalid_config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Invalid foundation model" in str(error) for error in result.errors))
    
    def test_validate_invalid_lambda_arn(self):
        """Test validation with invalid Lambda ARN."""
        invalid_config = self.valid_config
        invalid_config.action_groups[0].lambda_function_arn = "invalid-arn"
        
        result = self.validator.validate_agent_config(invalid_config)
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Invalid Lambda function ARN" in str(error) for error in result.errors))
    
    def test_validation_report_generation(self):
        """Test validation report generation."""
        result = self.validator.validate_agent_config(self.valid_config)
        report = self.validator.generate_validation_report(result)
        
        self.assertIn("✓ VALID", report)


class TestAgentConfigExtractor(unittest.TestCase):
    """Test cases for AgentConfigExtractor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock AWS responses
        self.mock_agent_response = {
            'agent': {
                'agentId': 'TESTID1234',
                'agentName': 'test-agent',
                'description': 'Test agent',
                'instruction': 'You are a test agent.',
                'foundationModel': 'anthropic.claude-3-5-sonnet-20241022-v2:0',
                'idleSessionTTLInSeconds': 1800,
                'agentResourceRoleArn': 'arn:aws:iam::123456789012:role/test-role'
            }
        }
        
        self.mock_action_groups_response = {
            'actionGroupSummaries': [
                {
                    'actionGroupId': 'AG12345678',
                    'actionGroupName': 'test-action'
                }
            ]
        }
        
        self.mock_action_group_detail = {
            'agentActionGroup': {
                'actionGroupId': 'AG12345678',
                'actionGroupName': 'test-action',
                'description': 'Test action group',
                'actionGroupExecutor': {
                    'lambda': 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
                },
                'apiSchema': {
                    'payload': json.dumps({
                        "openAPIVersion": "3.0.0",
                        "info": {"title": "Test API", "version": "1.0.0"},
                        "paths": {"/test": {"get": {"description": "Test endpoint", "parameters": {}}}}
                    })
                },
                'actionGroupState': 'ENABLED'
            }
        }
    
    @patch('boto3.client')
    def test_extract_agent_config(self, mock_boto_client):
        """Test agent configuration extraction."""
        # Mock Bedrock client
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        
        # Configure mock responses
        mock_client.get_agent.return_value = self.mock_agent_response
        mock_client.list_agent_aliases.return_value = {'agentAliasSummaries': []}
        mock_client.list_agent_action_groups.return_value = self.mock_action_groups_response
        mock_client.get_agent_action_group.return_value = self.mock_action_group_detail
        mock_client.list_agent_knowledge_bases.return_value = {'agentKnowledgeBaseSummaries': []}
        mock_client.list_tags_for_resource.return_value = {'tags': {}}
        
        # Create extractor and extract configuration
        extractor = AgentConfigExtractor(configs_dir=self.temp_dir)
        result = extractor.extract_agent_config('TESTID1234')
        
        # Verify extraction result
        self.assertTrue(result.success)
        self.assertIsNotNone(result.agent_config)
        self.assertEqual(result.agent_config.agent_name, 'test-agent')
        self.assertEqual(len(result.agent_config.action_groups), 1)
    
    @patch('boto3.client')
    def test_extract_agent_config_error(self, mock_boto_client):
        """Test agent configuration extraction with error."""
        # Mock Bedrock client to raise exception
        mock_client = Mock()
        mock_boto_client.return_value = mock_client
        mock_client.get_agent.side_effect = Exception("AWS API Error")
        
        # Create extractor and extract configuration
        extractor = AgentConfigExtractor(configs_dir=self.temp_dir)
        result = extractor.extract_agent_config('TESTID1234')
        
        # Verify error handling
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error_message)
        self.assertIn("AWS API Error", result.error_message)


class TestIntegration(unittest.TestCase):
    """Integration tests for configuration utilities."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.builder = AgentConfigBuilder(configs_dir=self.temp_dir)
        self.validator = AgentConfigValidator()
    
    def test_end_to_end_workflow(self):
        """Test complete workflow: build -> save -> load -> validate."""
        # Create sample configuration
        config_data = {
            "agent_name": "integration-test-agent",
            "description": "Integration test agent",
            "instructions": "You are an integration test agent.",
            "foundation_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "action_groups": [
                {
                    "name": "test-action",
                    "description": "Test action group",
                    "lambda_function_arn": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
                    "api_schema": {
                        "openAPIVersion": "3.0.0",
                        "info": {"title": "Test API", "version": "1.0.0"},
                        "paths": {"/test": {"get": {"description": "Test endpoint", "parameters": {}}}}
                    }
                }
            ]
        }
        
        # Build configuration
        agent_config = self.builder._build_agent_config(config_data)
        
        # Save configuration
        config_file = "integration-test.json"
        self.builder.save_agent_config(agent_config, config_file)
        
        # Load configuration
        loaded_config = self.builder.load_agent_config(config_file)
        
        # Validate configuration
        validation_result = self.validator.validate_agent_config(loaded_config)
        
        # Verify results
        self.assertEqual(loaded_config.agent_name, agent_config.agent_name)
        self.assertTrue(validation_result.is_valid)
        self.assertEqual(len(validation_result.errors), 0)


def run_tests():
    """Run all test cases."""
    print("Running Agent Configuration Utilities Tests")
    print("=" * 50)
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestAgentConfigBuilder))
    test_suite.addTest(unittest.makeSuite(TestAgentConfigValidator))
    test_suite.addTest(unittest.makeSuite(TestAgentConfigExtractor))
    test_suite.addTest(unittest.makeSuite(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall result: {'✓ PASSED' if success else '✗ FAILED'}")
    
    return success


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)