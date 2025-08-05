#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Test script to verify role assumption functionality for OSCAR metrics.
"""

import boto3
import json
from metrics.role_manager import RoleManager

def test_role_assumption():
    """Test assuming the oscar-metrics-vpc-lambda-role."""
    role_arn = "arn:aws:iam::395380602281:role/oscar-metrics-vpc-lambda-role"
    
    print(f"Testing role assumption for: {role_arn}")
    
    try:
        # Initialize role manager
        role_manager = RoleManager(role_arn)
        
        # Assume the role
        credentials = role_manager.assume_role()
        
        print("✅ Role assumption successful!")
        print(f"Access Key ID: {credentials.access_key[:10]}...")
        print(f"Has Session Token: {'Yes' if credentials.token else 'No'}")
        
        # Test using the assumed role credentials
        session = boto3.Session(
            aws_access_key_id=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_session_token=credentials.token
        )
        
        # Try to get caller identity with assumed role
        sts_client = session.client('sts')
        identity = sts_client.get_caller_identity()
        
        print(f"Assumed Role ARN: {identity['Arn']}")
        print("✅ Role assumption test completed successfully!")
        
    except Exception as e:
        print(f"❌ Role assumption failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    test_role_assumption()