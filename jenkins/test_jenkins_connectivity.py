#!/usr/bin/env python3
"""
Jenkins Connectivity Test Script

This script directly invokes the Jenkins Lambda function to test actual Jenkins
connectivity when proper network access is available. Use this with your mentor
to verify the Jenkins integration works end-to-end.
"""

import json
import boto3
import sys
import time
from typing import Dict, Any, Optional

class JenkinsConnectivityTester:
    """Test Jenkins connectivity through the Lambda function."""
    
    def __init__(self, function_name: str = "oscar-jenkins-agent", region: str = "us-east-1"):
        """Initialize the tester."""
        self.function_name = function_name
        self.region = region
        self.lambda_client = boto3.client('lambda', region_name=region)
        
    def invoke_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke the Lambda function with the given payload."""
        try:
            print(f"🚀 Invoking Lambda function: {self.function_name}")
            print(f"📤 Payload: {json.dumps(payload, indent=2)}")
            print("-" * 60)
            
            response = self.lambda_client.invoke(
                FunctionName=self.function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            print(f"📥 Lambda Status Code: {response.get('StatusCode', 'Unknown')}")
            
            # Check for function errors
            if response.get('FunctionError'):
                print(f"❌ Function Error: {response.get('FunctionError')}")
                print(f"📥 Error Response: {json.dumps(response_payload, indent=2)}")
                return {'status': 'lambda_error', 'error': response_payload}
            
            # Parse the body if it's a string
            if 'body' in response_payload and isinstance(response_payload['body'], str):
                try:
                    body = json.loads(response_payload['body'])
                    print(f"📋 Response: {json.dumps(body, indent=2)}")
                    return body
                except json.JSONDecodeError:
                    print(f"⚠️  Could not parse body as JSON: {response_payload['body']}")
                    return {'status': 'parse_error', 'raw_body': response_payload['body']}
            else:
                print(f"📋 Raw Response: {json.dumps(response_payload, indent=2)}")
                return response_payload
                
        except Exception as e:
            print(f"❌ Error invoking Lambda function: {e}")
            return {'status': 'invoke_error', 'error': str(e)}
    
    def test_connection(self) -> bool:
        """Test Jenkins connection."""
        print("🔍 Testing Jenkins Connection")
        print("=" * 60)
        
        payload = {
            "function": "test_connection",
            "parameters": []
        }
        
        result = self.invoke_function(payload)
        
        if result.get('status') == 'success':
            print("✅ Jenkins connection successful!")
            if 'jenkins_version' in result:
                print(f"📋 Jenkins Version: {result['jenkins_version']}")
            if 'num_executors' in result:
                print(f"📋 Executors: {result['num_executors']}")
            if 'username' in result:
                print(f"📋 Connected as: {result['username']}")
            return True
        else:
            print("❌ Jenkins connection failed!")
            if 'message' in result:
                print(f"📋 Error: {result['message']}")
            return False
    
    def test_docker_scan(self, image_name: str = "alpine:3.19") -> bool:
        """Test Docker scan job triggering."""
        print(f"\n🐳 Testing Docker Scan: {image_name}")
        print("=" * 60)
        
        payload = {
            "function": "docker_scan",
            "parameters": [
                {
                    "name": "image_name",
                    "value": image_name
                }
            ]
        }
        
        result = self.invoke_function(payload)
        
        if result.get('status') == 'success':
            print(f"✅ Docker scan triggered successfully for {image_name}!")
            if 'job_url' in result:
                print(f"🔗 Job URL: {result['job_url']}")
            if 'queue_location' in result:
                print(f"🔗 Queue Location: {result['queue_location']}")
            if 'parameters' in result:
                print(f"📋 Parameters: {result['parameters']}")
            return True
        else:
            print(f"❌ Docker scan failed for {image_name}!")
            if 'message' in result:
                print(f"📋 Error: {result['message']}")
            return False
    
    def test_job_info(self, job_name: str = "docker-scan") -> bool:
        """Test getting job information."""
        print(f"\n📋 Testing Job Info: {job_name}")
        print("=" * 60)
        
        payload = {
            "function": "get_job_info",
            "parameters": [
                {
                    "name": "job_name",
                    "value": job_name
                }
            ]
        }
        
        result = self.invoke_function(payload)
        
        if result.get('status') == 'success':
            print(f"✅ Job info retrieved for {job_name}!")
            if 'description' in result:
                print(f"📋 Description: {result['description']}")
            if 'parameter_definitions' in result:
                print(f"📋 Parameters: {json.dumps(result['parameter_definitions'], indent=2)}")
            return True
        else:
            print(f"❌ Failed to get job info for {job_name}!")
            if 'message' in result:
                print(f"📋 Error: {result['message']}")
            return False
    
    def test_list_jobs(self) -> bool:
        """Test listing available jobs."""
        print("\n📝 Testing List Jobs")
        print("=" * 60)
        
        payload = {
            "function": "list_jobs",
            "parameters": []
        }
        
        result = self.invoke_function(payload)
        
        if result.get('status') == 'success':
            print("✅ Jobs listed successfully!")
            if 'jobs' in result:
                print(f"📋 Available Jobs ({result.get('total_jobs', 0)}):")
                for job_name, job_info in result['jobs'].items():
                    print(f"  • {job_name}: {job_info.get('description', 'No description')}")
            return True
        else:
            print("❌ Failed to list jobs!")
            if 'message' in result:
                print(f"📋 Error: {result['message']}")
            return False
    
    def test_generic_job_trigger(self, job_name: str = "docker-scan", job_params: Optional[Dict[str, str]] = None) -> bool:
        """Test generic job triggering."""
        if job_params is None:
            job_params = {"IMAGE_FULL_NAME": "nginx:latest"}
        
        print(f"\n⚙️  Testing Generic Job Trigger: {job_name}")
        print("=" * 60)
        
        # Build parameters list
        parameters = [{"name": "job_name", "value": job_name}]
        for param_name, param_value in job_params.items():
            parameters.append({"name": param_name, "value": param_value})
        
        payload = {
            "function": "trigger_job",
            "parameters": parameters
        }
        
        result = self.invoke_function(payload)
        
        if result.get('status') == 'success':
            print(f"✅ Job {job_name} triggered successfully!")
            if 'job_url' in result:
                print(f"🔗 Job URL: {result['job_url']}")
            if 'parameters' in result:
                print(f"📋 Parameters: {result['parameters']}")
            return True
        else:
            print(f"❌ Failed to trigger job {job_name}!")
            if 'message' in result:
                print(f"📋 Error: {result['message']}")
            return False
    
    def run_comprehensive_test(self) -> None:
        """Run all tests comprehensively."""
        print("🚀 Jenkins Connectivity Comprehensive Test")
        print("=" * 80)
        print("This script tests actual Jenkins connectivity through the Lambda function.")
        print("Use this with your mentor when you have proper network access.")
        print("=" * 80)
        
        tests = []
        
        # Test 1: List Jobs (should always work)
        tests.append(("List Jobs", self.test_list_jobs()))
        
        # Test 2: Get Job Info (should always work)
        tests.append(("Get Job Info", self.test_job_info()))
        
        # Test 3: Test Connection (network dependent)
        tests.append(("Jenkins Connection", self.test_connection()))
        
        # Test 4: Docker Scan (network dependent)
        tests.append(("Docker Scan", self.test_docker_scan()))
        
        # Test 5: Generic Job Trigger (network dependent)
        tests.append(("Generic Job Trigger", self.test_generic_job_trigger()))
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 Test Summary:")
        passed = 0
        for test_name, result in tests:
            status = "PASS" if result else "FAIL"
            print(f"  {status:4} | {test_name}")
            if result:
                passed += 1
        
        print(f"\n🎯 Results: {passed}/{len(tests)} tests passed")
        
        if passed >= 2:  # At least the non-network tests should pass
            print("\n🎉 Core functionality is working!")
            if passed == len(tests):
                print("🌟 All tests passed - Jenkins integration is fully functional!")
            else:
                print("📡 Some network-dependent tests failed - this is expected without proper connectivity")
        else:
            print("\n⚠️  Core functionality issues detected - check Lambda function deployment")

def main():
    """Main function with command line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Jenkins connectivity through Lambda function")
    parser.add_argument("--function", default="oscar-jenkins-agent", help="Lambda function name")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--test", choices=["connection", "docker-scan", "job-info", "list-jobs", "trigger-job", "all"], 
                       default="all", help="Specific test to run")
    parser.add_argument("--image", default="alpine:3.19", help="Docker image for scan test")
    parser.add_argument("--job", default="docker-scan", help="Job name for job-specific tests")
    
    args = parser.parse_args()
    
    tester = JenkinsConnectivityTester(args.function, args.region)
    
    if args.test == "all":
        tester.run_comprehensive_test()
    elif args.test == "connection":
        tester.test_connection()
    elif args.test == "docker-scan":
        tester.test_docker_scan(args.image)
    elif args.test == "job-info":
        tester.test_job_info(args.job)
    elif args.test == "list-jobs":
        tester.test_list_jobs()
    elif args.test == "trigger-job":
        tester.test_generic_job_trigger(args.job)

if __name__ == "__main__":
    main()