#!/usr/bin/env python3
"""
Simple test script for job registration without requiring Jenkins credentials.
"""

import sys
import os

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock the config to avoid credential requirements
class MockConfig:
    def __init__(self):
        self.jenkins_url = "https://build.ci.opensearch.org"
        self.aws_region = "us-east-1"
        self.aws_account_id = "395380602281"
        self.jenkins_api_token = None
        self.request_timeout = 30
        self.log_level = "INFO"

# Replace the config import
import config
config.config = MockConfig()

from job_definitions import job_registry

def test_job_registration():
    """Test that jobs are properly registered."""
    print("🔧 Testing Job Registration...")
    
    jobs = job_registry.list_jobs()
    print(f"✅ Registered jobs: {jobs}")
    
    # Check for central release promotion job
    if 'Pipeline central-release-promotion' in jobs:
        print("✅ Central release promotion job is registered")
        
        # Get job info
        job_info = job_registry.get_job_info('Pipeline central-release-promotion')
        print(f"✅ Job description: {job_info['description']}")
        print(f"✅ Job parameters: {list(job_info['parameters'].keys())}")
        
        # Test parameter validation
        valid_params = {
            'RELEASE_VERSION': '2.11.0',
            'OPENSEARCH_RC_BUILD_NUMBER': '123',
            'OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER': '456'
        }
        
        try:
            validated = job_registry.validate_job_parameters('Pipeline central-release-promotion', valid_params)
            print(f"✅ Parameter validation successful: {validated}")
        except Exception as e:
            print(f"❌ Parameter validation failed: {e}")
            return False
        
        return True
    else:
        print("❌ Central release promotion job is NOT registered")
        return False

def main():
    """Run the test."""
    print("🚀 Testing Job Registration...\n")
    
    success = test_job_registration()
    
    if success:
        print("\n🎉 Job registration test passed!")
        print("\n📝 Usage:")
        print("   Job Name: 'Pipeline central-release-promotion'")
        print("   Required Parameters:")
        print("     - RELEASE_VERSION (e.g., '2.11.0')")
        print("     - OPENSEARCH_RC_BUILD_NUMBER (e.g., '123')")
        print("     - OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER (e.g., '456')")
        print("\n   Agent Usage:")
        print("   1. Agent calls get_job_info with job_name='Pipeline central-release-promotion'")
        print("   2. Agent learns about required parameters")
        print("   3. Agent calls trigger_job with job_name and all required parameters")
    else:
        print("\n❌ Job registration test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()