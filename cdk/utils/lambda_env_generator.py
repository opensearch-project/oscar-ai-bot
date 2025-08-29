#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Simple Lambda Environment Configuration Generator.

This utility generates basic Lambda environment configurations that reference
the Secrets Manager secret for use in CDK deployments.
"""

import json
from typing import Dict


def generate_lambda_env_config(secret_name: str = 'oscar-central-env', 
                              region: str = 'us-east-1') -> Dict[str, str]:
    """Generate basic Lambda environment configuration.
    
    Args:
        secret_name: Name of the secret containing environment variables
        region: AWS region
        
    Returns:
        Dictionary of environment variables for Lambda
    """
    return {
        'SECRET_NAME': secret_name,
        'AWS_REGION': region
    }


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Generate Lambda environment configurations'
    )
    parser.add_argument(
        '--secret-name',
        default='oscar-central-env',
        help='Name of the secret containing environment variables'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region'
    )
    
    args = parser.parse_args()
    
    config = generate_lambda_env_config(args.secret_name, args.region)
    print(json.dumps(config, indent=2))


if __name__ == '__main__':
    main()