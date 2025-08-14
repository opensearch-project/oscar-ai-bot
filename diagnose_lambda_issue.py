#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Diagnostic script to identify Lambda deployment issues.
"""

import os
import sys
import json

def check_environment_variables():
    """Check if all required environment variables are set."""
    print("🔍 Checking Environment Variables...")
    
    required_vars = [
        'OSCAR_BEDROCK_AGENT_ID',
        'OSCAR_BEDROCK_AGENT_ALIAS_ID',
        'SLACK_BOT_TOKEN',
        'SLACK_SIGNING_SECRET'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"   ✅ {var}: {'*' * min(len(value), 10)}")
        else:
            print(f"   ❌ {var}: NOT SET")
            missing_vars.append(var)
    
    return len(missing_vars) == 0

def test_config_initialization():
    """Test if config can be initialized."""
    print("\n🔍 Testing Config Initialization...")
    
    try:
        sys.path.append('oscar-agent')
        
        # Test without validation first
        from config import Config
        config_no_validation = Config(validate_required=False)
        print("   ✅ Config initialized without validation")
        
        # Test with validation
        try:
            config_with_validation = Config(validate_required=True)
            print("   ✅ Config initialized with validation")
            return True
        except ValueError as e:
            print(f"   ❌ Config validation failed: {e}")
            return False
            
    except Exception as e:
        print(f"   ❌ Config initialization failed: {e}")
        return False

def test_storage_initialization():
    """Test if storage can be initialized."""
    print("\n🔍 Testing Storage Initialization...")
    
    try:
        sys.path.append('oscar-agent')
        from storage import DynamoDBStorage
        
        storage = DynamoDBStorage()
        print("   ✅ Storage initialized")
        
        # Test table names
        print(f"   Context table: {storage.context_table.table_name}")
        print(f"   Sessions table: {storage.sessions_table.table_name}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Storage initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_initialization():
    """Test if OSCAR agent can be initialized."""
    print("\n🔍 Testing Agent Initialization...")
    
    try:
        sys.path.append('oscar-agent')
        from oscar_agent import get_oscar_agent
        
        agent = get_oscar_agent()
        print("   ✅ Agent initialized")
        print(f"   Agent ID: {agent.agent_id}")
        print(f"   Agent Alias: {agent.agent_alias_id}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Agent initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_slack_handler_initialization():
    """Test if Slack handler can be initialized."""
    print("\n🔍 Testing Slack Handler Initialization...")
    
    try:
        sys.path.append('oscar-agent')
        from slack_bolt import App
        from slack_handler import SlackHandler
        from storage import DynamoDBStorage
        from oscar_agent import get_oscar_agent
        
        # Create mock app
        app = App(token="dummy", signing_secret="dummy")
        storage = DynamoDBStorage()
        agent = get_oscar_agent()
        
        handler = SlackHandler(app, storage, agent)
        print("   ✅ Slack handler initialized")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Slack handler initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_lambda_function_status():
    """Check the current status of the Lambda function."""
    print("\n🔍 Checking Lambda Function Status...")
    
    try:
        import boto3
        
        function_name = "oscar-supervisor-agent"
        region = os.environ.get('AWS_REGION', 'us-east-1')
        
        lambda_client = boto3.client('lambda', region_name=region)
        
        # Get function configuration
        response = lambda_client.get_function(FunctionName=function_name)
        
        config = response['Configuration']
        print(f"   Function Name: {config['FunctionName']}")
        print(f"   Runtime: {config['Runtime']}")
        print(f"   State: {config['State']}")
        print(f"   Last Modified: {config['LastModified']}")
        print(f"   Code Size: {config['CodeSize']} bytes")
        
        # Check environment variables
        env_vars = config.get('Environment', {}).get('Variables', {})
        print(f"   Environment Variables: {len(env_vars)} set")
        
        # Check for recent errors
        if config['State'] != 'Active':
            print(f"   ⚠️  Function state is not Active: {config['State']}")
            if 'StateReason' in config:
                print(f"   Reason: {config['StateReason']}")
        
        return config['State'] == 'Active'
        
    except Exception as e:
        print(f"   ❌ Failed to check Lambda function: {e}")
        return False

def main():
    """Run all diagnostic tests."""
    print("🚀 Diagnosing Lambda Deployment Issues...\n")
    
    tests = [
        ("Environment Variables", check_environment_variables),
        ("Config Initialization", test_config_initialization),
        ("Storage Initialization", test_storage_initialization),
        ("Agent Initialization", test_agent_initialization),
        ("Slack Handler Initialization", test_slack_handler_initialization),
        ("Lambda Function Status", check_lambda_function_status),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n📊 Diagnostic Results:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print("=" * 50)
    print(f"   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"\n🎉 All diagnostics passed! The issue might be elsewhere.")
    else:
        print(f"\n❌ {total - passed} diagnostics failed.")
        print(f"\n🔧 Recommended Actions:")
        
        if not results.get("Environment Variables"):
            print("   1. Check that all required environment variables are set in .env")
            print("   2. Re-run the update script: ./update_slack_agent.sh")
        
        if not results.get("Config Initialization"):
            print("   3. Verify config.py has correct environment variable handling")
        
        if not results.get("Storage Initialization"):
            print("   4. Check DynamoDB table names and permissions")
            print("   5. Run: python setup_dynamodb_tables.py")
        
        if not results.get("Agent Initialization"):
            print("   6. Verify Bedrock agent ID and alias are correct")
            print("   7. Check Bedrock permissions")
        
        if not results.get("Lambda Function Status"):
            print("   8. Check Lambda function logs in CloudWatch")
            print("   9. Verify Lambda has correct IAM permissions")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())