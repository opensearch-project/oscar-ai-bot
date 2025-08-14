#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Setup and verify DynamoDB tables for OSCAR context preservation.

This script ensures the required DynamoDB tables exist with correct configuration.
"""

import boto3
import os
import sys
import time
from botocore.exceptions import ClientError

def create_context_table(dynamodb, table_name):
    """Create the context table if it doesn't exist."""
    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'thread_key',
                    'KeyType': 'HASH'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'thread_key',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        print(f"✅ Created context table: {table_name}")
        
        # Wait for table to be active
        print("   Waiting for table to be active...")
        table.wait_until_exists()
        
        # Enable TTL after table is active
        try:
            dynamodb.meta.client.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification={
                    'AttributeName': 'ttl',
                    'Enabled': True
                }
            )
            print("   ✅ TTL enabled")
        except Exception as e:
            print(f"   ⚠️  Could not enable TTL: {e}")
        
        print("   ✅ Table is active")
        
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"✅ Context table already exists: {table_name}")
            return True
        else:
            print(f"❌ Error creating context table: {e}")
            return False

def create_sessions_table(dynamodb, table_name):
    """Create the sessions table if it doesn't exist."""
    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'event_id',
                    'KeyType': 'HASH'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'event_id',
                    'AttributeType': 'S'
                }
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        
        print(f"✅ Created sessions table: {table_name}")
        
        # Wait for table to be active
        print("   Waiting for table to be active...")
        table.wait_until_exists()
        
        # Enable TTL after table is active
        try:
            dynamodb.meta.client.update_time_to_live(
                TableName=table_name,
                TimeToLiveSpecification={
                    'AttributeName': 'ttl',
                    'Enabled': True
                }
            )
            print("   ✅ TTL enabled")
        except Exception as e:
            print(f"   ⚠️  Could not enable TTL: {e}")
        
        print("   ✅ Table is active")
        
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"✅ Sessions table already exists: {table_name}")
            return True
        else:
            print(f"❌ Error creating sessions table: {e}")
            return False

def verify_table_configuration(dynamodb, table_name, expected_key):
    """Verify table configuration is correct."""
    try:
        table = dynamodb.Table(table_name)
        table.load()
        
        # Check key schema
        key_schema = table.key_schema
        if len(key_schema) == 1 and key_schema[0]['AttributeName'] == expected_key:
            print(f"   ✅ Key schema correct: {expected_key}")
        else:
            print(f"   ❌ Key schema incorrect: expected {expected_key}, got {key_schema}")
            return False
        
        # Check TTL configuration
        try:
            ttl_response = dynamodb.meta.client.describe_time_to_live(TableName=table_name)
            ttl_status = ttl_response.get('TimeToLiveDescription', {}).get('TimeToLiveStatus')
            if ttl_status == 'ENABLED':
                print(f"   ✅ TTL enabled")
            else:
                print(f"   ⚠️  TTL status: {ttl_status}")
        except Exception as e:
            print(f"   ⚠️  Could not check TTL: {e}")
        
        # Check billing mode
        billing_mode = table.billing_mode_summary
        if billing_mode and billing_mode.get('BillingMode') == 'PAY_PER_REQUEST':
            print(f"   ✅ Billing mode: PAY_PER_REQUEST")
        else:
            print(f"   ⚠️  Billing mode: {billing_mode}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error verifying table: {e}")
        return False

def test_table_access(dynamodb, table_name):
    """Test basic read/write access to the table."""
    try:
        table = dynamodb.Table(table_name)
        
        # Test write
        test_key = f"test_key_{int(time.time())}"
        test_item = {
            'thread_key' if 'context' in table_name else 'event_id': test_key,
            'test_data': 'test_value',
            'ttl': int(time.time()) + 300  # 5 minutes
        }
        
        table.put_item(Item=test_item)
        print(f"   ✅ Write test successful")
        
        # Test read
        response = table.get_item(
            Key={
                'thread_key' if 'context' in table_name else 'event_id': test_key
            }
        )
        
        if 'Item' in response:
            print(f"   ✅ Read test successful")
        else:
            print(f"   ❌ Read test failed: item not found")
            return False
        
        # Clean up test item
        table.delete_item(
            Key={
                'thread_key' if 'context' in table_name else 'event_id': test_key
            }
        )
        print(f"   ✅ Cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Table access test failed: {e}")
        return False

def main():
    """Setup and verify DynamoDB tables."""
    print("🚀 Setting up DynamoDB tables for OSCAR context preservation...\n")
    
    # Get configuration
    region = os.environ.get('AWS_REGION', 'us-east-1')
    context_table_name = os.environ.get('CONTEXT_TABLE_NAME', 'oscar-agent-context')
    sessions_table_name = os.environ.get('SESSIONS_TABLE_NAME', 'oscar-agent-sessions')
    
    print(f"Region: {region}")
    print(f"Context table: {context_table_name}")
    print(f"Sessions table: {sessions_table_name}")
    print()
    
    try:
        # Initialize DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # Setup context table
        print("📋 Setting up context table...")
        if create_context_table(dynamodb, context_table_name):
            print("🔍 Verifying context table configuration...")
            if verify_table_configuration(dynamodb, context_table_name, 'thread_key'):
                print("🧪 Testing context table access...")
                context_ok = test_table_access(dynamodb, context_table_name)
            else:
                context_ok = False
        else:
            context_ok = False
        
        print()
        
        # Setup sessions table
        print("📋 Setting up sessions table...")
        if create_sessions_table(dynamodb, sessions_table_name):
            print("🔍 Verifying sessions table configuration...")
            if verify_table_configuration(dynamodb, sessions_table_name, 'event_id'):
                print("🧪 Testing sessions table access...")
                sessions_ok = test_table_access(dynamodb, sessions_table_name)
            else:
                sessions_ok = False
        else:
            sessions_ok = False
        
        print()
        
        # Summary
        print("📊 Setup Summary:")
        print("=" * 40)
        print(f"Context table ({context_table_name}): {'✅ OK' if context_ok else '❌ FAILED'}")
        print(f"Sessions table ({sessions_table_name}): {'✅ OK' if sessions_ok else '❌ FAILED'}")
        print("=" * 40)
        
        if context_ok and sessions_ok:
            print("🎉 All tables are set up correctly!")
            
            # Show environment variables to set
            print("\n📝 Environment variables for your application:")
            print(f"export CONTEXT_TABLE_NAME={context_table_name}")
            print(f"export SESSIONS_TABLE_NAME={sessions_table_name}")
            print(f"export AWS_REGION={region}")
            
            return 0
        else:
            print("❌ Some tables failed setup. Please check the errors above.")
            return 1
            
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())