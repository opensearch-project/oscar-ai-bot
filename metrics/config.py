#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Configuration management for OSCAR metrics agents.
Optimized for VPC Lambda deployment with OpenSearch connectivity.
"""

import os
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Application configuration loaded from environment variables."""
    
    # OpenSearch VPC endpoint configuration
    opensearch_host: str
    opensearch_region: str
    opensearch_service: str
    opensearch_domain_arn: str
    
    # VPC configuration
    vpc_id: str
    subnet_ids: List[str]
    security_group_id: str
    
    # Role assumption configuration
    metrics_role_arn: str
    
    # Application settings
    log_level: str
    request_timeout: int
    max_results: int
    mock_mode: bool
    agent_type: str
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # OpenSearch configuration
        self.opensearch_host = os.getenv('OPENSEARCH_HOST', '')
        self.opensearch_region = os.getenv('OPENSEARCH_REGION', os.getenv('AWS_REGION', 'us-east-1'))
        self.opensearch_service = os.getenv('OPENSEARCH_SERVICE', 'es')
        self.opensearch_domain_arn = os.getenv('OPENSEARCH_DOMAIN_ARN', '')
        
        # VPC configuration
        self.vpc_id = os.getenv('VPC_ID', '')
        subnet_ids_str = os.getenv('SUBNET_IDS', '')
        self.subnet_ids = [s.strip() for s in subnet_ids_str.split(',') if s.strip()]
        self.security_group_id = os.getenv('SECURITY_GROUP_ID', '')
        
        # Role assumption configuration  
        self.metrics_role_arn = os.getenv('METRICS_ROLE_ARN', 'arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole')
        
        # Application settings
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
        self.max_results = int(os.getenv('MAX_RESULTS', '50'))
        self.mock_mode = os.getenv('MOCK_MODE', 'false').lower() == 'true'
        self.agent_type = os.getenv('AGENT_TYPE', 'test-metrics')
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Log configuration (without sensitive values)
        logger.info("OSCAR Metrics Agent Configuration:")
        logger.info(f"  Agent Type: {self.agent_type}")
        logger.info(f"  OpenSearch Region: {self.opensearch_region}")
        logger.info(f"  VPC ID: {self.vpc_id}")
        logger.info(f"  Subnets: {len(self.subnet_ids)} configured")
        logger.info(f"  Metrics Role ARN: {self.metrics_role_arn}")
        logger.info(f"  Mock Mode: {self.mock_mode}")
        
        # Validate configuration
        self.validate()
    
    def validate(self) -> None:
        """Validate required configuration for VPC deployment."""
        if not self.mock_mode:
            # OpenSearch validation
            if not self.opensearch_host:
                raise ValueError("OPENSEARCH_HOST must be set for VPC endpoint access")
            
            if not self.opensearch_domain_arn:
                raise ValueError("OPENSEARCH_DOMAIN_ARN must be set for cross-account access")
            
            # VPC validation
            if not self.vpc_id:
                raise ValueError("VPC_ID must be set for VPC Lambda deployment")
            
            if not self.subnet_ids:
                raise ValueError("SUBNET_IDS must be set for VPC Lambda deployment")
            
            if not self.security_group_id:
                raise ValueError("SECURITY_GROUP_ID must be set for VPC Lambda deployment")
            
            # Validate OpenSearch host format
            if not (self.opensearch_host.endswith('.es.amazonaws.com') or 
                   self.opensearch_host.startswith('https://')):
                logger.warning("OPENSEARCH_HOST should be a VPC endpoint URL ending with .es.amazonaws.com")
        
        logger.info("Configuration validation passed")