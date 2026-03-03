#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Jenkins Integration Configuration

This module provides centralized configuration for the Jenkins integration,
including job definitions, credentials, and environment settings.
"""

import logging
import os
from io import StringIO

import boto3
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class JenkinsConfig:
    """Centralized configuration for Jenkins integration."""

    def __init__(self):
        """Initialize configuration by loading .env from secrets manager and setting up all variables."""

        # Load environment variables from central secret
        self._load_env_from_secrets()

        # Load Jenkins API token from dedicated secret
        self.jenkins_api_token = self._load_jenkins_secret()

        # Jenkins Server Configuration
        self.jenkins_url = os.getenv('JENKINS_URL', 'https://build.ci.opensearch.org')

        # Lambda Configuration
        self.lambda_timeout = int(os.getenv('LAMBDA_TIMEOUT', '180'))
        self.lambda_memory_size = int(os.getenv('LAMBDA_MEMORY_SIZE', '512'))

        # Request Configuration
        self.request_timeout = int(os.getenv('JENKINS_REQUEST_TIMEOUT', '30'))
        self.max_retries = int(os.getenv('JENKINS_MAX_RETRIES', '3'))

        # Logging Configuration
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')

        # Validate required configuration
        self._validate_config()

    def _load_env_from_secrets(self) -> None:
        """Load environment variables from AWS Secrets Manager."""
        try:
            session = boto3.session.Session()
            client = session.client(
                service_name='secretsmanager',
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )

            # Get the .env content from secrets manager
            response = client.get_secret_value(SecretId='oscar-central-env-dev-cdk')
            env_content = response['SecretString']

            # Load the .env content into environment variables
            config_stream = StringIO(env_content)
            load_dotenv(stream=config_stream, override=True)

            logger.info("Successfully loaded environment variables from AWS Secrets Manager")

        except Exception as e:
            logger.error(f"Error loading environment from secrets manager: {e}")
            logger.warning("Falling back to local environment variables")
            # Continue with local environment variables if secrets manager fails

    def _load_jenkins_secret(self) -> str:
        """Load Jenkins API token from its dedicated secret."""
        secret_name = os.getenv('JENKINS_SECRET_NAME')
        if not secret_name:
            # Fallback to env var if no dedicated secret configured
            return os.getenv('JENKINS_API_TOKEN', '')

        try:
            session = boto3.session.Session()
            client = session.client(
                service_name='secretsmanager',
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            response = client.get_secret_value(SecretId=secret_name)
            logger.info(f"Loaded Jenkins API token from secret: {secret_name}")
            return response['SecretString']
        except Exception as e:
            logger.error(f"Error loading Jenkins secret '{secret_name}': {e}")
            # Fallback to env var
            return os.getenv('JENKINS_API_TOKEN', '')

    def _validate_config(self) -> None:
        """Validate that required configuration is present."""
        if not self.jenkins_url:
            raise ValueError("JENKINS_URL is required")

        if not self.jenkins_api_token:
            logger.warning("JENKINS_API_TOKEN is not configured")

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

    def get_workflow_url(self, job_name: str, build_number: int) -> str:
        """Get the workflow URL for a specific build."""
        return f"{self.jenkins_url}/job/{job_name}/{build_number}/"


class _ConfigProxy:
    """Proxy that caches config per lambda execution."""
    def __init__(self):
        self._cached_config = None
        self.aws_request_id = None
        self._lambda_request_id = None

    def set_request_id(self, request_id: str) -> None:
        """Set the AWS Lambda request ID."""
        self.aws_request_id = request_id

    def __getattr__(self, name):
        # If no config cached yet or request ID changed, create fresh config
        if self._cached_config is None or (self.aws_request_id and self._lambda_request_id != self.aws_request_id):
            self._cached_config = JenkinsConfig()
            self._lambda_request_id = self.aws_request_id

        return getattr(self._cached_config, name)


# Global configuration proxy
config = _ConfigProxy()
