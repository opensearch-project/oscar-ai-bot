#!/usr/bin/env python3
"""
Direct Docker Scan Script

This script allows you to trigger Docker scans directly via Lambda function
without going through the Bedrock agent. Useful for testing and direct execution.

Usage:
    python3 direct_docker_scan.py <image_name>
    python3 direct_docker_scan.py alpine:3.19
    python3 direct_docker_scan.py opensearchproject/opensearch:2.11.0
"""

import json
import boto3
import sys
import argparse

def invoke_docker_scan(image_name: str, function_name: str = "oscar-jenkins-agent", region: str = "us-east-1") -> dict:
    """
    Directly invoke the Jenkins Lambda function to trigger a Docker scan.
    
    Args:
        image_name: Docker image name to scan (e.g., alpine:3.19)
        function_name: Lambda function name
        region: AWS region
        
    Returns:
        Dictionary containing the scan result
    """
    lambda_client = boto3.client('lambda', region_name=region)
    
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
        print(f"🐳 Triggering Docker scan for: {image_name}")
        print(f"📡 Lambda function: {function_name}")
        print(f"🌍 Region: {region}")
        print("-" * 60)
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        print(f"📥 Lambda Status: {response.get('StatusCode', 'Unknown')}")
        
        # Check for function errors
        if response.get('FunctionError'):
            print(f"❌ Function Error: {response.get('FunctionError')}")
            print(f"📋 Error Details: {json.dumps(response_payload, indent=2)}")
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

def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Directly trigger Docker security scans via Jenkins Lambda function",
        epilog="""
Examples:
  python3 direct_docker_scan.py alpine:3.19
  python3 direct_docker_scan.py opensearchproject/opensearch:2.11.0
  python3 direct_docker_scan.py nginx:latest --function my-jenkins-function
  python3 direct_docker_scan.py ubuntu:22.04 --region us-west-2
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'image_name',
        help='Docker image name to scan (e.g., alpine:3.19, nginx:latest)'
    )
    parser.add_argument(
        '--function',
        default='oscar-jenkins-agent',
        help='Lambda function name (default: oscar-jenkins-agent)'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        print(f"🔧 Configuration:")
        print(f"   Image: {args.image_name}")
        print(f"   Function: {args.function}")
        print(f"   Region: {args.region}")
        print()
    
    # Validate image name format
    if ':' not in args.image_name:
        print("⚠️  Warning: Image name should include a tag (e.g., alpine:3.19)")
        print(f"   Using: {args.image_name}:latest")
        args.image_name = f"{args.image_name}:latest"
    
    # Invoke the scan
    result = invoke_docker_scan(args.image_name, args.function, args.region)
    
    # Print summary
    print("\n" + "=" * 60)
    if result.get('status') == 'success':
        print("🎉 Docker scan triggered successfully!")
        if 'job_url' in result:
            print(f"🔗 Monitor at: {result['job_url']}")
        if 'queue_location' in result:
            print(f"📍 Queue: {result['queue_location']}")
        if 'scan_info' in result:
            scan_info = result['scan_info']
            print(f"📊 Scan Type: {scan_info.get('scan_type', 'Unknown')}")
            print(f"📋 Note: {scan_info.get('note', '')}")
    else:
        print("❌ Docker scan failed!")
        if 'message' in result:
            print(f"📋 Error: {result['message']}")
        if 'error' in result and result['error'] != result.get('message'):
            print(f"🔍 Details: {result['error']}")
    
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if result.get('status') == 'success' else 1)

if __name__ == "__main__":
    main()