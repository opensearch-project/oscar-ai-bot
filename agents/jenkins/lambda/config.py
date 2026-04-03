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

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class JenkinsConfig:
    """Centralized configuration for Jenkins integration."""

    def __init__(self):
        """Initialize configuration by loading .env from secrets manager and setting up all variables."""

        # Load Jenkins API token from dedicated secret
        self.jenkins_api_token = self._load_jenkins_secret()

        # Jenkins Server Configuration (required)
        self.jenkins_url = os.environ.get('JENKINS_URL', '')

        # Request Configuration
        self.request_timeout = int(os.getenv('JENKINS_REQUEST_TIMEOUT', '30'))
        self.verify_ssl = os.getenv('JENKINS_VERIFY_SSL', 'true').lower() != 'false'

        # GitHub Configuration (for Jenkinsfile discovery)
        self.github_repo = os.environ.get('JENKINSFILE_GITHUB_REPO', '')
        self.github_branch = os.getenv('JENKINSFILE_GITHUB_BRANCH', 'main')
        self.jenkins_dir = os.getenv('JENKINSFILE_JENKINS_DIR', 'jenkins')
        _ignore_raw = os.getenv('JENKINSFILE_IGNORE_LIST', '')
        self.jenkinsfile_ignore_list = [p.strip() for p in _ignore_raw.split(',') if p.strip()]

        # Validate required configuration
        self._validate_config()

    def _load_jenkins_secret(self) -> str:
        """Load Jenkins API token exclusively from AWS Secrets Manager."""
        secret_name = os.getenv('JENKINS_SECRET_NAME')
        if not secret_name:
            logger.error("JENKINS_SECRET_NAME environment variable is not set")
            return ''

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
            logger.error(f"Failed to load Jenkins secret '{secret_name}': {e}")
            return ''

    def _validate_config(self) -> None:
        """Validate that required configuration is present."""
        if not self.jenkins_url:
            raise ValueError("JENKINS_URL environment variable is required")

        if not self.github_repo:
            raise ValueError("JENKINSFILE_GITHUB_REPO environment variable is required")

        if not self.jenkins_api_token:
            logger.warning("JENKINS_API_TOKEN is not configured")

    def get_job_url(self, job_name: str) -> str:
        """Get the full URL for a Jenkins job."""
        return f"{self.jenkins_url}/job/{job_name}"

    def get_build_with_parameters_url(self, job_name: str) -> str:
        """Get the buildWithParameters URL for a Jenkins job."""
        return f"{self.jenkins_url}/job/{job_name}/buildWithParameters"

    def get_build_api_url(self, job_name: str, build_number: int) -> str:
        """Get the API URL for a specific build."""
        return f"{self.jenkins_url}/job/{job_name}/{build_number}/api/json"

    def get_pipeline_describe_url(self, job_name: str, build_number: int) -> str:
        """Get the Pipeline Stage API URL for a build."""
        return f"{self.jenkins_url}/job/{job_name}/{build_number}/wfapi/describe"

    def get_stage_log_url(self, job_name: str, build_number: int, node_id: str) -> str:
        """Get the log URL for a specific pipeline stage."""
        return f"{self.jenkins_url}/job/{job_name}/{build_number}/execution/node/{node_id}/wfapi/log"

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
