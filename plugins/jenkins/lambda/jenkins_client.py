#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Jenkins Client Implementation

This module provides the core Jenkins client functionality for triggering jobs,
checking status, and managing Jenkins operations through the REST API.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

import requests
from config import config
from job_definitions import JobRegistry
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class JenkinsCredentials:
    """Manages Jenkins credentials from configuration."""

    def __init__(self):
        self._username: Optional[str] = None
        self._token: Optional[str] = None
        self._credentials_loaded = False

    def _load_credentials(self) -> None:
        """Load credentials from configuration (already loaded from secrets manager)."""
        if self._credentials_loaded:
            logger.info("JENKINS CREDENTIALS: Already loaded, skipping")
            return

        try:
            jenkins_api_token = config.jenkins_api_token

            if not jenkins_api_token:
                raise ValueError("JENKINS_API_TOKEN not found in configuration")

            if ':' in jenkins_api_token:
                self._username, self._token = jenkins_api_token.split(':', 1)
                self._username = self._username.strip()
                self._token = self._token.strip()
                self._credentials_loaded = True
            else:
                raise ValueError("Jenkins API token format should be 'username:token'")

        except Exception as e:
            raise Exception(f"Failed to load Jenkins credentials: {str(e)}")

    def get_auth(self) -> HTTPBasicAuth:
        """Get HTTP Basic Auth object for requests."""
        self._load_credentials()
        return HTTPBasicAuth(self._username, self._token)

    def get_username(self) -> str:
        """Get the Jenkins username."""
        self._load_credentials()
        return self._username

    def get_curl_auth_string(self) -> str:
        """Get the auth string for curl commands (for logging/debugging)."""
        self._load_credentials()
        return f"{self._username}:***"


class JenkinsClient:
    """Main Jenkins client for job operations."""

    def __init__(self, job_registry: JobRegistry):
        self.credentials = JenkinsCredentials()
        self.session = requests.Session()
        self.session.timeout = config.request_timeout
        self.session.verify = config.verify_ssl
        self.job_registry = job_registry

    def _get_build_number_from_queue(self, queue_location: str, auth: HTTPBasicAuth, max_attempts: int = 15) -> Optional[int]:
        """
        Poll the Jenkins queue to get the build number once the job starts executing.

        Args:
            queue_location: The queue location URL returned by Jenkins
            auth: Authentication object
            max_attempts: Maximum number of polling attempts

        Returns:
            Build number if found, None otherwise
        """
        try:
            # Convert queue location to API URL
            if not queue_location.endswith('/api/json'):
                api_url = queue_location.rstrip('/') + '/api/json'
            else:
                api_url = queue_location

            logger.info(f"JENKINS CLIENT: Polling queue for build number: {api_url}")

            for attempt in range(max_attempts):
                try:
                    response = self.session.get(api_url, auth=auth, timeout=5)

                    if response.status_code == 200:
                        queue_data = response.json()

                        # Check if the job has started executing (has executable field)
                        executable = queue_data.get('executable')
                        if executable and 'number' in executable:
                            build_number = executable['number']

                            return build_number

                        # If not yet executing, wait a bit before next attempt
                        if attempt < max_attempts - 1:
                            time.sleep(2)

                    elif response.status_code == 404:
                        # Queue item might have been processed and removed

                        break

                except requests.exceptions.RequestException as e:
                    logger.warning(f"JENKINS CLIENT: Error polling queue (attempt {attempt + 1}): {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(2)

            return None

        except Exception as e:
            logger.error(f"JENKINS CLIENT: Error getting build number from queue: {e}")
            return None

    def trigger_job(self, job_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger a Jenkins job with parameters.

        Args:
            job_name: Name of the Jenkins job
            parameters: Dictionary of job parameters

        Returns:
            Dictionary containing the result of the job trigger
        """
        try:

            # Validate job exists and parameters
            job_def = self.job_registry.get_job(job_name)
            if not job_def:
                logger.error(f"JENKINS CLIENT: Unknown job '{job_name}'")
                return {
                    'status': 'error',
                    'message': f'Unknown job: {job_name}',
                    'available_jobs': self.job_registry.list_jobs()
                }

            # Validate and normalize parameters
            try:
                validated_params = self.job_registry.validate_job_parameters(job_name, parameters)

            except ValueError as e:
                logger.error(f"JENKINS CLIENT: Parameter validation failed: {e}")
                return {
                    'status': 'error',
                    'message': f'Parameter validation failed: {str(e)}',
                    'job_info': self.job_registry.get_job_info(job_name)
                }

            # Build the request
            url = config.get_build_with_parameters_url(job_name)
            auth = self.credentials.get_auth()
            response = self.session.post(
                url,
                data=validated_params,
                auth=auth,
                allow_redirects=False  # Jenkins returns 201 with Location header
            )

            if response.status_code in [200, 201]:
                # Success - job triggered
                queue_location = response.headers.get('Location', '')

                result = {
                    'status': 'success',
                    'message': f'Successfully triggered Jenkins job: {job_name}',
                    'job_name': job_name,
                    'job_url': config.get_job_url(job_name),
                    'parameters': validated_params,
                    'http_status': response.status_code
                }

                if queue_location:
                    result['queue_location'] = queue_location

                    # Try to get the build number from the queue
                    build_number = self._get_build_number_from_queue(queue_location, auth)
                    if build_number:
                        result['build_number'] = build_number
                        result['workflow_url'] = config.get_workflow_url(job_name, build_number)

                return result

            else:
                # Error response
                error_message = response.text[:500] if response.text else 'Unknown error'
                return {
                    'status': 'error',
                    'message': f'Failed to trigger Jenkins job: {job_name}',
                    'error': f'HTTP {response.status_code}: {error_message}',
                    'http_status': response.status_code,
                    'job_url': config.get_job_url(job_name)
                }

        except requests.exceptions.Timeout:
            return {
                'status': 'error',
                'message': f'Request timed out after {config.request_timeout} seconds',
                'error': 'timeout',
                'job_name': job_name
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'status': 'error',
                'message': 'Failed to connect to Jenkins server',
                'error': f'Connection error: {str(e)}',
                'jenkins_url': config.jenkins_url
            }
        except Exception as e:
            logger.error(f"Unexpected error triggering job {job_name}: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': f'Unexpected error triggering job: {job_name}',
                'error': str(e)
            }

    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Jenkins server.

        Returns:
            Dictionary containing connection test results
        """
        try:
            url = f"{config.jenkins_url}/api/json"
            auth = self.credentials.get_auth()

            logger.info("Testing Jenkins connection")
            logger.info(f"URL: {url}")

            response = self.session.get(url, auth=auth)

            if response.status_code == 200:
                try:
                    jenkins_info = response.json()
                    return {
                        'status': 'success',
                        'message': 'Successfully connected to Jenkins',
                        'jenkins_version': jenkins_info.get('version', 'unknown'),
                        'node_name': jenkins_info.get('nodeName', 'unknown'),
                        'num_executors': jenkins_info.get('numExecutors', 0),
                        'jenkins_url': config.jenkins_url,
                        'username': self.credentials.get_username()
                    }
                except json.JSONDecodeError:
                    return {
                        'status': 'success',
                        'message': 'Successfully connected to Jenkins',
                        'jenkins_url': config.jenkins_url,
                        'username': self.credentials.get_username(),
                        'note': 'Connected but could not parse server info'
                    }
            else:
                return {
                    'status': 'error',
                    'message': f'Jenkins connection failed with HTTP status: {response.status_code}',
                    'error': response.text[:200] if response.text else 'No error details',
                    'http_status': response.status_code,
                    'jenkins_url': config.jenkins_url
                }

        except requests.exceptions.Timeout:
            return {
                'status': 'error',
                'message': f'Connection test timed out after {config.request_timeout} seconds',
                'error': 'timeout',
                'jenkins_url': config.jenkins_url
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'status': 'error',
                'message': 'Failed to connect to Jenkins server',
                'error': f'Connection error: {str(e)}',
                'jenkins_url': config.jenkins_url
            }
        except Exception as e:
            logger.error(f"Unexpected error testing connection: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': 'Unexpected error testing Jenkins connection',
                'error': str(e),
                'jenkins_url': config.jenkins_url
            }

    def get_build_status(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Get the status of a specific Jenkins build.

        Args:
            job_name: Name of the Jenkins job
            build_number: Build number to check

        Returns:
            Dictionary containing build status information
        """
        try:
            url = config.get_build_api_url(job_name, build_number)
            auth = self.credentials.get_auth()

            logger.info(f"Getting build status for {job_name} #{build_number}")
            response = self.session.get(url, auth=auth)

            if response.status_code == 200:
                build_info = response.json()
                building = build_info.get('building', False)
                result_value = build_info.get('result')

                if building:
                    status = 'IN_PROGRESS'
                elif result_value:
                    status = result_value  # SUCCESS, FAILURE, ABORTED, UNSTABLE
                else:
                    status = 'UNKNOWN'

                duration_ms = build_info.get('duration', 0)
                duration_str = f"{duration_ms // 60000}m {(duration_ms % 60000) // 1000}s" if duration_ms else "N/A"

                return {
                    'status': 'success',
                    'job_name': job_name,
                    'build_number': build_number,
                    'build_status': status,
                    'duration': duration_str,
                    'display_name': build_info.get('displayName', f'#{build_number}'),
                    'timestamp': build_info.get('timestamp'),
                    'build_url': config.get_workflow_url(job_name, build_number),
                }
            elif response.status_code == 404:
                return {
                    'status': 'error',
                    'message': f'Build #{build_number} not found for job {job_name}',
                    'job_url': config.get_job_url(job_name),
                }
            else:
                return {
                    'status': 'error',
                    'message': f'Failed to get build status: HTTP {response.status_code}',
                    'http_status': response.status_code,
                    'build_url': config.get_workflow_url(job_name, build_number),
                }

        except requests.exceptions.Timeout:
            return {
                'status': 'error',
                'message': f'Request timed out after {config.request_timeout} seconds',
                'job_name': job_name,
                'build_number': build_number,
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'status': 'error',
                'message': 'Failed to connect to Jenkins server',
                'error': f'Connection error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Error getting build status for {job_name} #{build_number}: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': 'Unexpected error getting build status',
                'error': str(e),
            }

    def get_build_failure_details(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Get failure details using the Pipeline Stage API.

        Identifies FAILED and UNSTABLE stages and fetches their logs.
        Falls back to console tail for non-pipeline jobs.
        """
        max_log_lines = 100

        try:
            url = config.get_pipeline_describe_url(job_name, build_number)
            auth = self.credentials.get_auth()

            logger.info(f"Getting pipeline details for {job_name} #{build_number}")
            response = self.session.get(url, auth=auth)

            if response.status_code == 404:
                return self._get_console_tail(job_name, build_number, auth, max_log_lines)

            if response.status_code != 200:
                return {
                    'status': 'error',
                    'message': f'Failed to get pipeline details: HTTP {response.status_code}',
                    'build_url': config.get_workflow_url(job_name, build_number),
                }

            pipeline_info = response.json()
            stages = pipeline_info.get('stages', [])

            problem_stages = [
                s for s in stages
                if s.get('status') in ('FAILED', 'UNSTABLE')
            ]
            skipped_stages = [
                s.get('name') for s in stages
                if s.get('status') == 'NOT_EXECUTED'
            ]

            if not problem_stages:
                return {
                    'status': 'success',
                    'job_name': job_name,
                    'build_number': build_number,
                    'build_status': pipeline_info.get('status', 'UNKNOWN'),
                    'message': 'No failed or unstable stages found',
                    'total_stages': len(stages),
                    'build_url': config.get_workflow_url(job_name, build_number),
                }

            failed_stage_details = []
            for stage in problem_stages:
                node_id = str(stage.get('id', ''))
                stage_name = stage.get('name', 'unknown')
                duration_ms = stage.get('durationMillis', 0)
                duration_str = f"{duration_ms // 60000}m {(duration_ms % 60000) // 1000}s" if duration_ms else "N/A"

                # Error info from the describe response (always available for Groovy/pipeline errors)
                error_info = stage.get('error', {})
                error_message = error_info.get('message', '')
                error_type = error_info.get('type', '')

                # Get the actual error log by drilling into child step nodes
                log_excerpt = ''
                log_node_id = node_id
                if node_id:
                    log_excerpt, log_node_id = self._get_stage_error_log(
                        job_name, build_number, node_id, auth, max_log_lines
                    )

                # If still empty, fall back to full console tail
                if not log_excerpt and not error_message:
                    log_excerpt = self._get_console_tail_text(job_name, build_number, auth, max_log_lines)

                # Build the log URL pointing to the specific step node
                step_log_url = f"{config.jenkins_url}/job/{job_name}/{build_number}/execution/node/{log_node_id}/log/" if log_node_id else ''

                failed_stage_details.append({
                    'name': stage_name,
                    'stage_status': stage.get('status'),
                    'duration': duration_str,
                    'error_message': error_message,
                    'error_type': error_type,
                    'stage_log_url': step_log_url,
                    'log_excerpt': log_excerpt,
                })

            return {
                'status': 'success',
                'job_name': job_name,
                'build_number': build_number,
                'build_status': pipeline_info.get('status', 'UNKNOWN'),
                'total_stages': len(stages),
                'failed_stages': failed_stage_details,
                'skipped_stages': skipped_stages,
                'build_url': config.get_workflow_url(job_name, build_number),
            }

        except requests.exceptions.Timeout:
            return {
                'status': 'error',
                'message': f'Request timed out after {config.request_timeout} seconds',
                'job_name': job_name,
                'build_number': build_number,
            }
        except requests.exceptions.ConnectionError as e:
            return {
                'status': 'error',
                'message': 'Failed to connect to Jenkins server',
                'error': f'Connection error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Error getting failure details for {job_name} #{build_number}: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': 'Unexpected error getting build failure details',
                'error': str(e),
            }

    def _get_stage_error_log(
        self, job_name: str, build_number: int, stage_node_id: str,
        auth: HTTPBasicAuth, max_lines: int
    ) -> tuple:
        """Get error log for a stage by drilling into its child step nodes.

        The stage-level wfapi/log is often empty. The actual error is in the
        child stageFlowNodes — find the failed step and fetch its log.

        Returns:
            Tuple of (log_text, node_id_for_url). node_id is the specific step
            node whose /execution/node/{id}/log/ URL shows the error.
        """
        try:
            # First try the stage-level log
            log_url = config.get_stage_log_url(job_name, build_number, stage_node_id)
            log_resp = self.session.get(log_url, auth=auth)
            if log_resp.status_code == 200:
                content_type = log_resp.headers.get('content-type', '')
                if content_type.startswith('application/json'):
                    raw_text = log_resp.json().get('text', '')
                else:
                    raw_text = log_resp.text
                if raw_text:
                    return self._truncate(raw_text, max_lines), stage_node_id

            # Stage log empty — drill into child step nodes
            describe_url = f"{config.jenkins_url}/job/{job_name}/{build_number}/execution/node/{stage_node_id}/wfapi/describe"
            desc_resp = self.session.get(describe_url, auth=auth)
            if desc_resp.status_code == 200:
                stage_detail = desc_resp.json()
                for step_node in stage_detail.get('stageFlowNodes', []):
                    if step_node.get('status') in ('FAILED', 'UNSTABLE'):
                        step_id = str(step_node.get('id', ''))
                        if step_id:
                            step_log_url = config.get_stage_log_url(job_name, build_number, step_id)
                            step_log_resp = self.session.get(step_log_url, auth=auth)
                            if step_log_resp.status_code == 200:
                                content_type = step_log_resp.headers.get('content-type', '')
                                if content_type.startswith('application/json'):
                                    raw_text = step_log_resp.json().get('text', '')
                                else:
                                    raw_text = step_log_resp.text
                                if raw_text:
                                    return self._truncate(raw_text, max_lines), step_id
        except Exception as e:
            logger.warning(f"Failed to get stage error log for node {stage_node_id}: {e}")

        return '', stage_node_id

    @staticmethod
    def _truncate(text: str, max_lines: int) -> str:
        """Truncate text to the last max_lines lines."""
        lines = text.splitlines()
        if len(lines) > max_lines:
            return f"... (truncated, showing last {max_lines} lines)\n" + '\n'.join(lines[-max_lines:])
        return text

    def _get_console_tail_text(self, job_name: str, build_number: int, auth: HTTPBasicAuth, max_lines: int) -> str:
        """Fetch last N lines of console output as plain text."""
        try:
            url = f"{config.jenkins_url}/job/{job_name}/{build_number}/consoleText"
            response = self.session.get(url, auth=auth)
            if response.status_code == 200:
                lines = response.text.splitlines()
                if len(lines) > max_lines:
                    return f"... (truncated, showing last {max_lines} lines)\n" + '\n'.join(lines[-max_lines:])
                return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch console text: {e}")
        return ''

    def _get_console_tail(self, job_name: str, build_number: int, auth: HTTPBasicAuth, max_lines: int) -> Dict[str, Any]:
        """Fallback: fetch last N lines of console output for non-pipeline jobs."""
        excerpt = self._get_console_tail_text(job_name, build_number, auth, max_lines)
        if excerpt:
            return {
                'status': 'success',
                'job_name': job_name,
                'build_number': build_number,
                'message': 'Pipeline stage API not available, showing console tail',
                'log_excerpt': excerpt,
                'build_url': config.get_workflow_url(job_name, build_number),
            }
        return {
            'status': 'error',
            'message': 'Failed to get console output',
            'build_url': config.get_workflow_url(job_name, build_number),
        }

    def get_job_info(self, job_name: str) -> Dict[str, Any]:
        """
        Get information about a Jenkins job.

        Args:
            job_name: Name of the Jenkins job

        Returns:
            Dictionary containing job information
        """
        try:

            # Check if we know about this job
            job_def = self.job_registry.get_job(job_name)
            if not job_def:
                logger.warning(f"JENKINS CLIENT: Unknown job '{job_name}'")
                return {
                    'status': 'error',
                    'message': f'Unknown job: {job_name}',
                    'available_jobs': self.job_registry.list_jobs()
                }

            # Return job definition info (don't need to call Jenkins API for this)
            result = {
                'status': 'success',
                'job_name': job_name,
                'description': job_def.description,
                'job_url': config.get_job_url(job_name),
                'parameter_definitions': job_def.get_parameter_info(),
                'jenkins_url': config.jenkins_url
            }

            return result

        except Exception as e:
            logger.error(f"Error getting job info for {job_name}: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': f'Error getting job info: {job_name}',
                'error': str(e)
            }

    def list_available_jobs(self) -> Dict[str, Any]:
        """
        List all available Jenkins jobs that this client supports.

        Returns:
            Dictionary containing available jobs and their information
        """
        jobs_info = {}
        for job_name in self.job_registry.list_jobs():
            jobs_info[job_name] = self.job_registry.get_job_info(job_name)

        return {
            'status': 'success',
            'message': 'Available Jenkins jobs',
            'jobs': jobs_info,
            'total_jobs': len(jobs_info)
        }
