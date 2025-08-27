#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.


#!/usr/bin/env python3
"""
Debug script to check authorization configuration
"""
import os
import sys
sys.path.append('oscar-agent')

from config import config

def debug_authorization():
    print("=== OSCAR Authorization Debug ===")
    print(f"AWS Region: {config.region}")
    print()
    
    print("DM Authorized Users:")
    for i, user in enumerate(config.dm_authorized_users, 1):
        print(f"  {i}. {user}")
    print()
    
    print("Fully Authorized Users:")
    for i, user in enumerate(config.fully_authorized_users, 1):
        print(f"  {i}. {user}")
    print()
    
    # Test a specific user ID
    test_user = input("Enter your user ID to test: ").strip()
    if test_user:
        dm_authorized = test_user in config.dm_authorized_users
        fully_authorized = test_user in config.fully_authorized_users
        
        print(f"\nUser {test_user} authorization:")
        print(f"  DM Authorized: {dm_authorized}")
        print(f"  Fully Authorized: {fully_authorized}")
        print(f"  Should use privileged agent: {fully_authorized}")
        print(f"  Should use limited agent: {not fully_authorized}")

if __name__ == "__main__":
    debug_authorization()