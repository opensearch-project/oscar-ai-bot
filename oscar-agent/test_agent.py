#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Test script for OSCAR Agent functionality.

This script can be used to test the OSCAR agent integration locally.
"""

import os
import sys
import logging
from typing import Optional

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from oscar_agent import get_oscar_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_agent_configuration():
    """Test that the agent configuration is valid."""
    try:
        logger.info("Testing OSCAR agent configuration...")
        logger.info(f"Agent ID: {config.oscar_bedrock_agent_id}")
        logger.info(f"Agent Alias ID: {config.oscar_bedrock_agent_alias_id}")
        logger.info(f"Region: {config.region}")
        
        if not config.oscar_bedrock_agent_id or config.oscar_bedrock_agent_id == "YOUR_AGENT_ID_HERE":
            logger.error("OSCAR_BEDROCK_AGENT_ID is not set or is placeholder value")
            return False
        
        if not config.oscar_bedrock_agent_alias_id:
            logger.error("OSCAR_BEDROCK_AGENT_ALIAS_ID is not set")
            return False
        
        logger.info("Agent configuration looks valid")
        return True
        
    except Exception as e:
        logger.error(f"Error testing agent configuration: {e}")
        return False

def test_agent_query(query: str = "What is OpenSearch?"):
    """Test a simple agent query."""
    try:
        logger.info(f"Testing agent query: {query}")
        
        # Get the agent
        agent = get_oscar_agent()
        
        # Make a test query
        response, session_id = agent.query(query)
        
        logger.info(f"Agent response: {response[:200]}...")
        logger.info(f"Session ID: {session_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error testing agent query: {e}")
        return False

def main():
    """Main test function."""
    logger.info("Starting OSCAR agent tests...")
    
    # Test configuration
    if not test_agent_configuration():
        logger.error("Agent configuration test failed")
        return False
    
    # Test agent query
    if not test_agent_query():
        logger.error("Agent query test failed")
        return False
    
    logger.info("All tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)