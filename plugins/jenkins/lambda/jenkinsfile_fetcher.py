#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
GitHub Jenkinsfile Fetcher for OSCAR.

Fetches Jenkinsfiles from GitHub at Lambda cold start, parses them
with JenkinsfileParser, builds a JobRegistry, and caches the result.
"""

import logging
import os
import time
from typing import Optional

import requests
from jenkinsfile_parser import JenkinsfileParser, ParsedJob
from job_definitions import JobRegistry

logger = logging.getLogger(__name__)

# Jenkinsfile paths to fetch (relative to repo root).
JENKINSFILE_PATHS = [
    "jenkins/docker/docker-scan.jenkinsfile",
    "jenkins/release-workflows/release-promotion.jenkinsfile",
    "jenkins/release-workflows/release-chores.jenkinsfile",
]

GITHUB_REPO = os.environ.get("JENKINSFILE_GITHUB_REPO", "gaiksaya/opensearch-build")
GITHUB_BRANCH = os.environ.get("JENKINSFILE_GITHUB_BRANCH", "main")
FETCH_TIMEOUT = int(os.environ.get("JENKINSFILE_FETCH_TIMEOUT", "5"))
CACHE_TTL = int(os.environ.get("JENKINSFILE_CACHE_TTL", "3600"))

# Module-level cache
_cached_registry: Optional[JobRegistry] = None
_cache_timestamp: float = 0.0


def _build_raw_url(path: str) -> str:
    """Build a raw.githubusercontent.com URL for a file."""
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"


def _fetch_jenkinsfile(path: str) -> Optional[str]:
    """Fetch a single Jenkinsfile from GitHub. Returns content or None on error."""
    url = _build_raw_url(path)
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT)
        if resp.status_code == 200:
            return resp.text
        logger.error(f"GitHub returned {resp.status_code} for {url}")
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
    return None


def _fetch_and_parse_all() -> JobRegistry:
    """Fetch all configured Jenkinsfiles, parse them, and build a JobRegistry."""
    parser = JenkinsfileParser()
    registry = JobRegistry()
    fetched = 0

    for path in JENKINSFILE_PATHS:
        content = _fetch_jenkinsfile(path)
        if content is None:
            logger.warning(f"Skipping {path} (fetch failed)")
            continue

        try:
            parsed_job: ParsedJob = parser.parse(content, path)
            registry.load_parsed_job(parsed_job)
            fetched += 1
            logger.info(f"Loaded job '{parsed_job.job_name}' from {path} ({len(parsed_job.parameters)} params)")
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")

    logger.info(f"Job registry built: {fetched}/{len(JENKINSFILE_PATHS)} Jenkinsfiles loaded")
    return registry


def get_job_registry() -> JobRegistry:
    """Get the cached JobRegistry, rebuilding if stale or missing."""
    global _cached_registry, _cache_timestamp

    now = time.time()
    if _cached_registry is not None and (now - _cache_timestamp) < CACHE_TTL:
        return _cached_registry

    logger.info("Building job registry from GitHub Jenkinsfiles")
    _cached_registry = _fetch_and_parse_all()
    _cache_timestamp = now
    return _cached_registry
