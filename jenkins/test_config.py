#!/usr/bin/env python3
"""
Test script to verify Jenkins configuration is working properly.
"""

import logging
import sys
import os

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from jenkins_client import JenkinsClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_config():
    """Test that configuration is loaded properly."""
    print("🔧 Testing Jenkins Configuration...")
    
    try:
        print(f"✅ Jenkins URL: {config.jenkins_url}")
        print(f"✅ AWS Region: {config.aws_region}")
        print(f"✅ AWS Account ID: {config.aws_account_id}")
        print(f"✅ Lambda Function Name: {config.jenkins_lambda_function_name}")
        print(f"✅ Request Timeout: {config.request_timeout}")
        print(f"✅ Log Level: {config.log_level}")
        
        # Check if Jenkins API token is loaded (don't print the actual token)
        if config.jenkins_api_token:
            print(f"✅ Jenkins API Token: Loaded (length: {len(config.jenkins_api_token)})")
        else:
            print("❌ Jenkins API Token: Not loaded")
            
        if config.jenkins_agent_id:
            print(f"✅ Jenkins Agent ID: {config.jenkins_agent_id}")
        else:
            print("⚠️  Jenkins Agent ID: Not set")
            
        if config.jenkins_agent_alias_id:
            print(f"✅ Jenkins Agent Alias ID: {config.jenkins_agent_alias_id}")
        else:
            print("⚠️  Jenkins Agent Alias ID: Not set")
        
        print("\n🎉 Configuration test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_jenkins_client():
    """Test that Jenkins client can be initialized."""
    print("\n🔧 Testing Jenkins Client...")
    
    try:
        client = JenkinsClient()
        print("✅ Jenkins client initialized successfully")
        
        # Test connection (this will actually try to connect to Jenkins)
        print("🌐 Testing Jenkins connection...")
        result = client.test_connection()
        
        if result['status'] == 'success':
            print("✅ Jenkins connection test successful!")
            print(f"   Jenkins Version: {result.get('jenkins_version', 'unknown')}")
            print(f"   Username: {result.get('username', 'unknown')}")
        else:
            print(f"❌ Jenkins connection test failed: {result.get('message', 'unknown error')}")
            
        return result['status'] == 'success'
        
    except Exception as e:
        print(f"❌ Jenkins client test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting Jenkins Configuration Tests...\n")
    
    config_ok = test_config()
    client_ok = test_jenkins_client()
    
    print(f"\n📊 Test Results:")
    print(f"   Configuration: {'✅ PASS' if config_ok else '❌ FAIL'}")
    print(f"   Jenkins Client: {'✅ PASS' if client_ok else '❌ FAIL'}")
    
    if config_ok and client_ok:
        print("\n🎉 All tests passed! Jenkins integration is ready.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the configuration.")
        sys.exit(1)

if __name__ == "__main__":
    main()