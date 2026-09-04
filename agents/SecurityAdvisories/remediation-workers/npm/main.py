# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entrypoint for the npm/yarn ecosystem remediation Fargate task.

The task is dispatched via ``ecs.run_task`` with the remediation payload passed
as container environment variables (``containerOverrides.environment``), so this
reads those env vars into an event dict and calls ``remediation.handle``.

Expected environment variables:
    REPO_NAME, CVE_ID, PACKAGE, PATCHED_VERSION   (the core inputs)
    INSTALLED_VERSION, BASE_BRANCH                (optional; base defaults main)
    SLACK_CHANNEL, SLACK_THREAD_TS                (optional; empty => log only)
"""

import logging
import os
import sys

import npm
import remediation

# Fargate has no Lambda-runtime log handler; without this, INFO logs are dropped.
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# Env var name -> event key. The worker reads every value with
# ``.get(key) or ""`` + strip, so a missing var is safe (treated as absent).
_ENV_TO_EVENT = {
    "REPO_NAME": "repo_name",
    "CVE_ID": "cve_id",
    "PACKAGE": "package",
    "PATCHED_VERSION": "patched_version",
    "INSTALLED_VERSION": "installed_version",
    "BASE_BRANCH": "base_branch",
    "SLACK_CHANNEL": "slack_channel",
    "SLACK_THREAD_TS": "slack_thread_ts",
}


def _event_from_env():
    """Build the remediation event dict from environment variables."""
    return {key: os.environ.get(env, "") for env, key in _ENV_TO_EVENT.items()}


def main():
    event = _event_from_env()
    logger.info("npm remediation (ECS) invoked: cve_id=%s repo_name=%s package=%s",
                event.get("cve_id"), event.get("repo_name"), event.get("package"))
    result = remediation.handle(event, npm)
    # Surface a non-zero exit on failure so the ECS task's stopped-reason /
    # exit code reflects the outcome (the Slack post-back is the user-facing
    # signal; this is for task-level observability).
    status = (result or {}).get("status")
    logger.info("npm remediation (ECS) finished: status=%s", status)
    return 0 if status in ("success", "no_change") else 1


if __name__ == "__main__":
    sys.exit(main())
