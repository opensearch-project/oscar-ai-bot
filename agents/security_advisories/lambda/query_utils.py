#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared utilities for Security Advisories query modules.

This module provides common helpers used across the DSL query builder and
tickets query builder, including version/tag resolution and standardized
error response construction.

Functions:
    resolve_version_tag: Map user-provided version to canonical tag format
    error_response: Return a consistent error response dict
    connection_error: Return a sanitized connection error response
"""

import logging
import re
from typing import Any, Dict, Optional

import semver

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Strict two-part numeric pattern (e.g., "3.7", "2.19") to avoid
# misclassifying pre-release/build metadata strings like "3.7-rc".
_TWO_PART_RE = re.compile(r'^\d+\.\d+$')


def _classify_version(version: str) -> str:
    """Classify a version string into a known category for dispatch.

    Returns one of: 'origin_prefixed', 'main_alias', 'three_part', 'two_part', 'unknown'.
    """
    if version.startswith('origin/'):
        return 'origin_prefixed'
    if version.lower() in ('main', 'latest'):
        return 'main_alias'
    try:
        semver.Version.parse(version)
        return 'three_part'
    except (ValueError, TypeError):
        pass
    if _TWO_PART_RE.match(version):
        try:
            semver.Version.parse(f'{version}.0')
            return 'two_part'
        except (ValueError, TypeError):
            pass
    return 'unknown'


def resolve_version_tag(version: str) -> str:
    """Map a user-provided version string to the canonical project.tag format.

    The scans and tickets indices store release branch tags as
    ``origin/{major}.{minor}`` and specific release version tags as
    three-part semver (e.g., ``2.19.6``).

    Mapping rules:
      - Already prefixed with ``"origin/"`` → returned as-is
      - ``"main"`` or ``"latest"`` → ``"origin/main"``
      - Two-part version (e.g., ``"3.7"``) → ``"origin/3.7"`` (branch tag)
      - Three-part version (e.g., ``"3.7.0"``, ``"2.19.6"``) → ``"origin/3.7"``, ``"origin/2.19"`` (branch tag)
      - Non-parseable input → returned as-is (for exact tag lookups)

    Args:
        version: User-provided version or tag string.

    Returns:
        The canonical tag string to use in queries.
    """
    if not version:
        return version

    match _classify_version(version):
        case 'origin_prefixed':
            resolved = version
        case 'main_alias':
            resolved = 'origin/main'
        case 'three_part':
            parsed = semver.Version.parse(version)
            resolved = f'origin/{parsed.major}.{parsed.minor}'
        case 'two_part':
            resolved = f'origin/{version}'
        case _:
            resolved = version

    logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
    return resolved


def error_response(
    error_type: str,
    message: str,
    status_code: Optional[int] = None,
) -> Dict[str, Any]:
    """Return a consistent error response dict.

    Args:
        error_type: Category of the error (e.g., opensearch_error, connection_error).
        message: Human-readable error description.
        status_code: Optional HTTP status code from OpenSearch.

    Returns:
        Error dict with status, type, retryable, message, and optional status_code.
    """
    error: Dict[str, Any] = {
        'status': 'error',
        'type': error_type,
        'retryable': False,
        'message': message,
    }

    if status_code is not None:
        error['status_code'] = status_code

    return error


def connection_error(exception: Exception) -> Dict[str, Any]:
    """Return a connection error without leaking internal details.

    Logs the original exception internally for diagnostics, then returns
    a sanitized error dict via error_response for consistent structure.

    Args:
        exception: The caught exception from the connection failure.

    Returns:
        Sanitized error dict with consistent structure.
    """
    logger.error(f'CONNECTION_ERROR: {type(exception).__name__}: {exception}')
    return error_response(
        'connection_error',
        'Failed to connect to the OpenSearch cluster. '
        'The service may be temporarily unavailable.',
    )
