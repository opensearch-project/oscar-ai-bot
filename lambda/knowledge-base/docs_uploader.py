#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Documentation uploader Lambda function.

This Lambda function fetches markdown files from specified GitHub repositories
and uploads them to S3, only uploading files that have changed (based on MD5 hash).
"""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Maximum directory depth to process
MAX_DEPTH = 3

# Paths to exclude from sync
EXCLUDE_PATTERNS = [
    '.github/*',
    'maintainers.md',
    'MAINTAINERS.md',
    'ADMINS*',
    'CODE_OF_CONDUCT.md',
    'CONTRIBUTING.md',
    'LICENSE.md',
    'NOTICE.md',
    '.gitignore*',
    'node_modules/*',
    'build/*',
    'dist/*',
    'target/*',
    '.git/*'
]


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler to clone GitHub repos and sync to S3."""
    temp_dir = None
    try:
        repos = event.get('repositories', [])
        bucket = os.environ.get('BUCKET_NAME')

        if not repos or not bucket:
            return {'statusCode': 400, 'message': 'Missing repositories or bucket'}

        logger.info(f"Processing {len(repos)} repositories")

        # Create temp directory
        temp_dir = tempfile.mkdtemp()

        for repo in repos:
            clone_repository(repo, temp_dir)

        # Sync to S3
        sync_output = sync_to_s3(temp_dir, bucket)

        return {
            'statusCode': 200,
            'message': f'Successfully synced {len(repos)} repositories',
            'sync_output': sync_output
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {'statusCode': 500, 'message': f'Error: {str(e)}'}
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def clone_repository(repo: str, temp_dir: str) -> None:
    """Clone a GitHub repository and keep only markdown files."""
    try:
        repo_name = repo.split('/')[-1]
        repo_path = os.path.join(temp_dir, repo_name)
        repo_url = f"https://github.com/{repo}.git"

        logger.info(f"Cloning {repo_url}")

        subprocess.run(
            ['git', 'clone', '--depth', '1', '--single-branch', repo_url, repo_path],
            check=True,
            capture_output=True,
            text=True
        )

        logger.info(f"Cloned {repo} to {repo_path}")

        # Remove non-markdown files and excluded patterns
        cleanup_non_markdown_files(repo_path)

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to clone {repo}: {e.stderr}")
        raise


def cleanup_non_markdown_files(repo_path: str) -> None:
    """Remove all non-markdown files and excluded patterns from cloned repo."""
    excluded_dirs = {'.git', 'node_modules', 'build', 'dist', 'target', '.github'}
    excluded_files = {'maintainers.md', 'code_of_conduct.md', 'contributing.md',
                      'license.md', 'notice.md', '.gitignore'}

    # First pass: remove excluded directories
    for item in os.listdir(repo_path):
        item_path = os.path.join(repo_path, item)
        if os.path.isdir(item_path) and item in excluded_dirs:
            shutil.rmtree(item_path)

    # Second pass: clean up files
    for root, dirs, files in os.walk(repo_path, topdown=False):
        for file in files:
            file_path = os.path.join(root, file)
            file_lower = file.lower()

            if not file.endswith('.md') or file_lower in excluded_files or file_lower.startswith('admins'):
                os.remove(file_path)

        # Remove empty directories
        if root != repo_path and not os.listdir(root):
            os.rmdir(root)


def sync_to_s3(local_dir: str, bucket: str) -> str:
    """Sync local directory to S3 using aws s3 sync."""
    try:
        cmd = [
            'aws', 's3', 'sync',
            local_dir,
            f's3://{bucket}/',
            '--delete'
        ]

        logger.info("Running s3 sync with delete")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        logger.info(f"Sync completed: {result.stdout}")
        return result.stdout

    except subprocess.CalledProcessError as e:
        logger.error(f"S3 sync failed: {e.stderr}")
        raise
