#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Simple deployment script for OSCAR CDK infrastructure.

This script provides a straightforward interface to deploy the complete OSCAR infrastructure.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def validate_prerequisites() -> bool:
    """Validate deployment prerequisites."""
    logger = logging.getLogger(__name__)
    
    # Check CDK CLI
    try:
        result = subprocess.run(['cdk', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error("CDK CLI not available")
            return False
        logger.info(f"CDK CLI version: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logger.error("CDK CLI not available or not working")
        return False
    
    # Check required environment variables
    required_vars = ['CDK_DEFAULT_ACCOUNT', 'CDK_DEFAULT_REGION']
    for var in required_vars:
        if not os.environ.get(var):
            logger.error(f"Required environment variable {var} not set")
            return False
    
    logger.info("Prerequisites validation passed")
    return True

def deploy_stacks(stacks: list = None, verbose: bool = False) -> bool:
    """Deploy CDK stacks."""
    logger = logging.getLogger(__name__)
    
    # Change to CDK directory
    cdk_dir = Path(__file__).parent.parent
    original_cwd = os.getcwd()
    
    try:
        os.chdir(cdk_dir)
        
        # Build command
        cmd = ['cdk', 'deploy']
        
        if stacks:
            cmd.extend(stacks)
        else:
            cmd.append('--all')
        
        cmd.extend([
            '--require-approval', 'never',
            '--progress', 'events' if verbose else 'bar'
        ])
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        # Run deployment
        result = subprocess.run(cmd, timeout=3600)  # 1 hour timeout
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        logger.error("Deployment timed out")
        return False
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        return False
    finally:
        os.chdir(original_cwd)

def main():
    """Main entry point for deployment."""
    parser = argparse.ArgumentParser(
        description='Deploy OSCAR infrastructure using CDK'
    )
    parser.add_argument(
        '--stacks',
        nargs='+',
        help='Specific stacks to deploy (default: all)'
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip prerequisite validation'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("🚀 Starting OSCAR infrastructure deployment")
        
        # Validate prerequisites
        if not args.skip_validation:
            if not validate_prerequisites():
                logger.error("❌ Prerequisites validation failed")
                sys.exit(1)
        
        # Deploy stacks
        success = deploy_stacks(args.stacks, args.verbose)
        
        if success:
            logger.info("🎉 Deployment completed successfully!")
        else:
            logger.error("❌ Deployment failed!")
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Deployment failed with unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()