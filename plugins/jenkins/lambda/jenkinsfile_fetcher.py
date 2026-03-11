#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
GitHub Jenkinsfile Fetcher for OSCAR.

Dynamically discovers Jenkinsfiles under the jenkins/ directory of the
opensearch-build repo, fetches them from GitHub, parses with
JenkinsfileParser, builds a JobRegistry, and caches the result.
"""

import logging
import time
from typing import List, Optional

import requests
from config import config
from jenkinsfile_parser import JenkinsfileParser, ParsedJob
from job_definitions import JobRegistry

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
FETCH_TIMEOUT = 5
CACHE_TTL = 3600


def _is_ignored(path: str) -> bool:
    """Check if a path matches any entry in the ignore list (exact or prefix)."""
    for ignored in config.jenkinsfile_ignore_list:
        if path == ignored or path.startswith(ignored.rstrip("/") + "/"):
            return True
    return False


# Module-level cache
_cached_registry: Optional[JobRegistry] = None
_cache_timestamp: float = 0.0


def _github_api_url(path: str) -> str:
    """Build a GitHub API URL for listing directory contents."""
    return f"https://api.github.com/repos/{config.github_repo}/contents/{path}?ref={config.github_branch}"


def _build_raw_url(path: str) -> str:
    """Build a raw.githubusercontent.com URL for a file."""
    return f"https://raw.githubusercontent.com/{config.github_repo}/{config.github_branch}/{path}"


def _discover_jenkinsfiles(directory: str = None) -> List[str]:
    """Recursively discover all .jenkinsfile files under the given directory using the GitHub API."""
    if directory is None:
        directory = config.jenkins_dir
    paths: List[str] = []
    dirs_to_visit = [directory]

    while dirs_to_visit:
        current_dir = dirs_to_visit.pop()
        url = _github_api_url(current_dir)
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT)
            if resp.status_code != 200:
                logger.error(f"GitHub API returned {resp.status_code} for {url}")
                continue

            for item in resp.json():
                item_path = item.get("path", "")
                if _is_ignored(item_path):
                    logger.info(f"Ignoring {item_path} (in ignore list)")
                    continue
                if item.get("type") == "dir":
                    dirs_to_visit.append(item_path)
                elif item.get("type") == "file" and item_path.endswith(".jenkinsfile"):
                    paths.append(item_path)

        except requests.RequestException as e:
            logger.error(f"Failed to list {current_dir}: {e}")

    logger.info(f"Discovered {len(paths)} Jenkinsfiles under {directory}")
    return paths


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
    """Discover, fetch, and parse all Jenkinsfiles into a JobRegistry."""
    parser = JenkinsfileParser()
    registry = JobRegistry()

    jenkinsfile_paths = _discover_jenkinsfiles()
    loaded = 0
    skipped_no_annotation = 0

    for path in jenkinsfile_paths:
        content = _fetch_jenkinsfile(path)
        if content is None:
            logger.warning(f"Skipping {path} (fetch failed)")
            continue

        try:
            parsed_job: ParsedJob = parser.parse(content, path)
            registry.load_parsed_job(parsed_job)
            loaded += 1
            logger.info(f"Loaded job '{parsed_job.job_name}' from {path} ({len(parsed_job.parameters)} params)")
        except ValueError:
            # No @job-name annotation — not an OSCAR-managed job, skip silently
            skipped_no_annotation += 1
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")

    logger.info(
        f"Job registry built: {loaded} loaded, "
        f"{skipped_no_annotation} skipped (no annotation), "
        f"{len(jenkinsfile_paths)} total discovered"
    )
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
