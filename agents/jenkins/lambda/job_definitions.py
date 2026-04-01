#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Jenkins Job Definitions

Provides the data model and registry for Jenkins jobs. Job definitions
are populated at runtime by parsing Jenkinsfiles fetched from GitHub
(see jenkinsfile_fetcher.py), rather than being hand-coded here.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class JobParameter:
    """Represents a Jenkins job parameter with validation."""
    name: str
    description: str
    required: bool = True
    default_value: Optional[str] = None
    parameter_type: str = "string"  # string, boolean, choice, activeChoice, reactiveChoice
    choices: Optional[List[str]] = None
    validation_pattern: Optional[str] = None
    referenced_parameters: Optional[str] = None
    choice_map: Optional[Dict[str, List[str]]] = field(default_factory=lambda: None)


class JobDefinition:
    """A job definition populated from parsed Jenkinsfile data."""

    def __init__(self, job_name: str, description: str, parameters: List[JobParameter]):
        self.job_name = job_name
        self.description = description
        self.parameters = parameters

    def validate_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize parameters for this job.

        Args:
            params: Dictionary of parameter name -> value

        Returns:
            Dictionary of validated parameters

        Raises:
            ValueError: If required parameters are missing or invalid
        """
        validated = {}

        for param_def in self.parameters:
            param_name = param_def.name
            param_value = params.get(param_name)

            # Check required parameters
            if param_def.required and param_value is None:
                if param_def.default_value is not None:
                    param_value = param_def.default_value
                else:
                    raise ValueError(f"Required parameter '{param_name}' is missing")

            # Skip None values for optional parameters
            if param_value is None:
                if param_def.default_value is not None:
                    param_value = param_def.default_value
                else:
                    continue

            # Validate choices (flat list)
            if param_def.choices and param_value not in param_def.choices:
                raise ValueError(
                    f"Parameter '{param_name}' must be one of {param_def.choices}, got '{param_value}'"
                )

            # Validate reactive choice against choice_map
            if param_def.choice_map and param_def.referenced_parameters:
                parent_value = params.get(param_def.referenced_parameters)
                if parent_value and parent_value in param_def.choice_map:
                    valid_choices = param_def.choice_map[parent_value]
                    if param_value not in valid_choices:
                        raise ValueError(
                            f"Parameter '{param_name}' must be one of {valid_choices} "
                            f"when {param_def.referenced_parameters}='{parent_value}', "
                            f"got '{param_value}'"
                        )

            # Validate pattern before type conversion (needs string value)
            if param_def.validation_pattern and param_def.parameter_type == "string":
                import re
                str_value = str(param_value)
                if not re.match(param_def.validation_pattern, str_value):
                    raise ValueError(
                        f"Parameter '{param_name}' does not match required pattern. "
                        f"Expected format for {param_def.description.lower()}"
                    )

            # Type conversion
            if param_def.parameter_type == "boolean":
                if isinstance(param_value, str):
                    param_value = param_value.lower() in ('true', '1', 'yes', 'on')
                param_value = bool(param_value)
            elif param_def.parameter_type == "string":
                param_value = str(param_value)

            validated[param_name] = param_value

        return validated

    def get_parameter_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all parameters for this job."""
        param_info = {}
        for param in self.parameters:
            info: Dict[str, Any] = {
                'description': param.description,
                'required': param.required,
                'type': param.parameter_type,
                'default': param.default_value,
                'choices': param.choices,
            }
            if param.validation_pattern:
                info['validation_pattern'] = param.validation_pattern
            if param.referenced_parameters:
                info['referenced_parameters'] = param.referenced_parameters
            if param.choice_map:
                info['choice_map'] = param.choice_map
            param_info[param.name] = info
        return param_info


class JobRegistry:
    """Registry for managing available Jenkins jobs."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobDefinition] = {}

    def load_parsed_job(self, parsed_job: Any) -> None:
        """Load a job from a ParsedJob (from jenkinsfile_parser).

        Args:
            parsed_job: A ParsedJob dataclass instance.
        """
        parameters = [
            JobParameter(
                name=p.name,
                description=p.description,
                required=p.required,
                default_value=p.default_value,
                parameter_type=p.parameter_type,
                choices=p.choices,
                referenced_parameters=p.referenced_parameters,
                choice_map=p.choice_map,
            )
            for p in parsed_job.parameters
        ]

        job_def = JobDefinition(
            job_name=parsed_job.job_name,
            description=parsed_job.description,
            parameters=parameters,
        )
        self.register_job(job_def)

    def register_job(self, job_definition: JobDefinition) -> None:
        """Register a job definition."""
        self._jobs[job_definition.job_name] = job_definition
        logger.info(f"Registered Jenkins job: {job_definition.job_name}")

    def get_job(self, job_name: str) -> Optional[JobDefinition]:
        """Get a job definition by name."""
        return self._jobs.get(job_name)

    def list_jobs(self) -> List[str]:
        """List all registered job names."""
        return list(self._jobs.keys())

    def get_job_info(self, job_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a job."""
        job = self.get_job(job_name)
        if not job:
            return None

        return {
            'name': job.job_name,
            'description': job.description,
            'parameters': job.get_parameter_info()
        }

    def validate_job_parameters(self, job_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters for a specific job."""
        job = self.get_job(job_name)
        if not job:
            raise ValueError(f"Unknown job: {job_name}")

        return job.validate_parameters(params)
