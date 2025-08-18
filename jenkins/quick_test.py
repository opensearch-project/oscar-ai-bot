#!/usr/bin/env python3
"""
Quick Jenkins Test Script

Simple script to quickly test specific Jenkins functions.
Perfect for testing with your mentor when you get connectivity.
"""

import json
import boto3
import sys

def test_docker_scan(image_name="alpine:3.19"):
    """Quick test of Docker scan functionality."""
    print(f"🐳 Testing Docker scan for: {image_name}")
    print("-" * 50)
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    payload = {
        "function": "docker_scan",
        "parameters": [
            {
                "name": "image_name",
                "value": image_name
            }
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-jenkins-agent',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if 'body' in result:
            body = json.loads(result['body'])
            print(f"📋 Result: {json.dumps(body, indent=2)}")
            
            if body.get('status') == 'success':
                print(f"✅ SUCCESS: Docker scan triggered for {image_name}")
                if 'job_url' in body:
                    print(f"🔗 Monitor at: {body['job_url']}")
                return True
            else:
                print(f"❌ FAILED: {body.get('message', 'Unknown error')}")
                return False
        else:
            print(f"📋 Raw response: {json.dumps(result, indent=2)}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_connection():
    """Quick test of Jenkins connection."""
    print("🔍 Testing Jenkins connection...")
    print("-" * 50)
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    payload = {
        "function": "test_connection",
        "parameters": []
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-jenkins-agent',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if 'body' in result:
            body = json.loads(result['body'])
            print(f"📋 Result: {json.dumps(body, indent=2)}")
            
            if body.get('status') == 'success':
                print("✅ SUCCESS: Connected to Jenkins")
                if 'jenkins_version' in body:
                    print(f"📋 Jenkins version: {body['jenkins_version']}")
                if 'username' in body:
                    print(f"📋 Connected as: {body['username']}")
                return True
            else:
                print(f"❌ FAILED: {body.get('message', 'Unknown error')}")
                return False
        else:
            print(f"📋 Raw response: {json.dumps(result, indent=2)}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main function."""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("Usage:")
        print("  python3 quick_test.py connection")
        print("  python3 quick_test.py scan [image_name]")
        print("  python3 quick_test.py both [image_name]")
        print("")
        print("Examples:")
        print("  python3 quick_test.py connection")
        print("  python3 quick_test.py scan alpine:3.19")
        print("  python3 quick_test.py scan opensearchproject/opensearch:2.11.0")
        print("  python3 quick_test.py both nginx:latest")
        sys.exit(0 if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help'] else 1)
    
    command = sys.argv[1]
    image_name = sys.argv[2] if len(sys.argv) > 2 else "alpine:3.19"
    
    print("🚀 Quick Jenkins Test")
    print("=" * 50)
    
    if command == "connection":
        success = test_connection()
    elif command == "scan":
        success = test_docker_scan(image_name)
    elif command == "both":
        print("Testing both connection and Docker scan...")
        print("")
        conn_success = test_connection()
        print("")
        scan_success = test_docker_scan(image_name)
        success = conn_success and scan_success
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
    
    print("")
    print("=" * 50)
    if success:
        print("🎉 Test completed successfully!")
    else:
        print("⚠️  Test failed - check network connectivity and Jenkins access")

if __name__ == "__main__":
    main()