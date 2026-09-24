# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entrypoint for the maven/Gradle ecosystem remediation Fargate task.

The task is dispatched via ``ecs.run_task`` with the remediation payload passed
as container environment variables (``containerOverrides.environment``), so this
reads those env vars into an event dict and calls ``remediation.handle``.

Expected environment variables:
    REPO_NAME, CVE_ID, PACKAGE, PATCHED_VERSION   (the core inputs)
    INSTALLED_VERSION, BASE_BRANCH                (optional; base defaults main)
    DECLARATION_CLASS, ORIGIN_FILES               (optional; maven routing signals)
    SLACK_CHANNEL, SLACK_THREAD_TS                (optional; empty => log only)

ORIGIN_FILES is a JSON-encoded list of the distinct build.gradle files the
coordinate resolves in (distilled from the scan's ``package.origin`` by the Lambda);
it decodes to ``event['origin_files']`` for force-target selection. Absent/blank
=> ``[]``.
"""

import json
import logging
import os
import sys

import maven
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
    "DECLARATION_CLASS": "declaration_class",
    "BASE_BRANCH": "base_branch",
    "SLACK_CHANNEL": "slack_channel",
    "SLACK_THREAD_TS": "slack_thread_ts",
}


def _parse_origin_files(raw):
    """Decode the JSON ORIGIN_FILES env into a list of build.gradle paths.

    Env vars are strings, so it arrives JSON-encoded (see remediation_handler
    payload). A blank/missing var or unparseable JSON yields ``[]`` — the worker
    then behaves as if origin were absent (keeps its declaration-scan behavior /
    root fallback), never crashing on the transport.
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("ORIGIN_FILES env is not valid JSON; treating as absent.")
        return []
    return value if isinstance(value, list) else []


def _event_from_env():
    """Build the remediation event dict from environment variables."""
    event = {key: os.environ.get(env, "") for env, key in _ENV_TO_EVENT.items()}
    event["origin_files"] = _parse_origin_files(os.environ.get("ORIGIN_FILES", ""))
    return event


def main():
    event = _event_from_env()
    logger.info("maven remediation (ECS) invoked: cve_id=%s repo_name=%s package=%s",
                event.get("cve_id"), event.get("repo_name"), event.get("package"))
    result = remediation.handle(event, maven)
    # Surface the outcome via the task exit code for observability (the Slack
    # post-back is the user-facing signal).
    status = (result or {}).get("status")
    logger.info("maven remediation (ECS) finished: status=%s", status)
    return 0 if status in remediation.CLEAN_WORKER_STATUSES else 1


if __name__ == "__main__":
    sys.exit(main())
