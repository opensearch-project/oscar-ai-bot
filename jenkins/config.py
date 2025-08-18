#!/usr/bin/env python3
"""
Jenkins Integration Configuration

This module provides centralized configuration for the Jenkins integration,
including job definitions, credentials, and environment settings.
"""

import os
from typing import Dict, Any, Optional

class JenkinsConfig:
    """Centralized configuration for Jenkins integration."""
    
    def __init__(self):
        """Initialize configuration with environment variables and defaults."""
        
        # Jenkins Server Configuration
        self.jenkins_url = os.getenv('JENKINS_URL', 'https://ci-staging.opensearch.org')
        self.jenkins_secret_name = os.getenv('JENKINS_SECRET_NAME', 'jenkins-api-token')
        self.jenkins_secret_arn = os.getenv(
            'JENKINS_SECRET_ARN', 
            'arn:aws:secretsmanager:us-east-1:395380602281:secret:jenkins-api-token-WQZEc6'
        )
        
        # AWS Configuration
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.aws_account_id = os.getenv('AWS_ACCOUNT_ID', '395380602281')
        
        # Lambda Configuration
        self.lambda_timeout = int(os.getenv('LAMBDA_TIMEOUT', '180'))
        self.lambda_memory_size = int(os.getenv('LAMBDA_MEMORY_SIZE', '512'))
        
        # Request Configuration
        self.request_timeout = int(os.getenv('JENKINS_REQUEST_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('JENKINS_MAX_RETRIES', '3'))
        
        # Logging Configuration
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        
    def get_job_url(self, job_name: str) -> str:
        """Get the full URL for a Jenkins job."""
        return f"{self.jenkins_url}/job/{job_name}"
    
    def get_build_with_parameters_url(self, job_name: str) -> str:
        """Get the buildWithParameters URL for a Jenkins job."""
        return f"{self.jenkins_url}/job/{job_name}/buildWithParameters"
    
    def get_job_api_url(self, job_name: str) -> str:
        """Get the API URL for a Jenkins job."""
        return f"{self.jenkins_url}/job/{job_name}/api/json"
    
    def get_build_api_url(self, job_name: str, build_number: int) -> str:
        """Get the API URL for a specific build."""
        return f"{self.jenkins_url}/job/{job_name}/{build_number}/api/json"

# Global configuration instance
config = JenkinsConfig()