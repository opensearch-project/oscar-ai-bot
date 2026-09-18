# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""LLM edit-planner for the maven remediation worker.

Given the CVE inputs and the repo's ``build.gradle`` file(s), ask a Bedrock model
*how* the target coordinate's version is declared — i.e. which deterministic edit
to apply, or that it's out of scope. The model returns a small JSON "plan"; it
never emits file contents (the deterministic code applies the edit).

Deliberately narrow so the model can't hallucinate the important values:
  - the coordinate (group:artifact) and patched version come from ``ctx`` (verified
    upstream by the SecurityAdvisories pre-flight), NOT the model;
  - the model only classifies the declaration (literal / in-repo ext var /
    out-of-scope / already-patched) and names where it is;
  - the output is validated against a fixed schema, and the caller re-verifies the
    named literal/var actually exists before editing (never trusts the model to
    locate it).

On any failure (Bedrock error, empty/invalid output, schema violation) this returns
``None`` so the caller falls back to the deterministic scanner — same pattern as npm.
"""

import json
import logging
import os

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cross-region inference profile ("us." prefix); overridable, default matches npm.
MODEL_ID = os.environ.get(
    "REMEDIATION_LLM_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
MAX_TOKENS = 512
TEMPERATURE = 0  # a classification/routing decision, not prose

# Allowed actions per mode, and which of them must name a "target" (the literal
# version / ext-var name / catalog key to edit). out_of_scope + none never name one.
_ACTIONS = {
    "plugin": {"edit_literal", "edit_ext_var", "out_of_scope", "none"},
    "catalog": {"catalog", "out_of_scope", "none"},
}
_TARGET_ACTIONS = {"edit_literal", "edit_ext_var", "catalog"}

_client = None


def _runtime():
    """Lazily construct the Bedrock client (needs a region; created on first use)."""
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            config=BotoConfig(read_timeout=60, connect_timeout=10,
                              retries={"max_attempts": 2}),
        )
    return _client


_SYSTEM = (
    "You route maven/Gradle CVE fixes. Given a repo's Gradle build files and a "
    "target coordinate + patched version, classify HOW the coordinate's version is "
    "declared. Reply with ONLY a JSON object, no markdown or prose."
)

_CATALOG_PROMPT = """\
Target coordinate: {coordinate}
Target version (already verified — do not change it): {patched_version}
Currently installed: {installed_version}

This repository uses a Gradle version catalog. Its [libraries] entries map a
coordinate (group + name) to a version via version.ref, which names a key in the
[versions] table. Find the [versions] key that drives {coordinate}'s version.

gradle/libs.versions.toml:
{gradle_sources}

Choose exactly one action and return JSON of the form:
{{"action": "<action>", "file": "gradle/libs.versions.toml",
  "target": "<the [versions] key name, or empty for out_of_scope/none>",
  "reason": "<one short sentence on how {coordinate} maps to a [versions] key>"}}

Actions:
- "catalog": {coordinate} has a [libraries] entry whose version.ref points at a key
  in [versions]. "target" = that [versions] key name (e.g. "log4j"), NOT the
  version. A key may be shared by a family of libraries — that is expected.
- "out_of_scope": {coordinate} has no [libraries] entry (it isn't in the catalog),
  or its entry pins an inline version rather than a version.ref. "target" empty.
- "none": the [versions] key is already at or above {patched_version}. "target" empty.

Return only the JSON object."""

_PROMPT = """\
Target coordinate: {coordinate}
Target version (already verified — do not change it): {patched_version}
Currently installed: {installed_version}

build.gradle file(s):
{gradle_sources}

Choose exactly one action and return JSON of the form:
{{"action": "<action>", "file": "<relative build.gradle path or empty>",
  "target": "<the version literal, or the ext-var name; empty for out_of_scope/none>",
  "reason": "<one short sentence on where {coordinate} is declared and why>"}}

Actions:
- "edit_literal": {coordinate} is declared with a hardcoded version literal (a
  `force`/direct-dep line like "group:artifact:1.2.3"). "target" = that literal
  version string (e.g. "1.2.3"); "file" = the build.gradle it's in.
- "edit_ext_var": {coordinate}'s version is a reference to an in-repo variable
  defined in this repo (e.g. ext {{ foo_version = '1.2.3' }} used as
  "...:${{foo_version}}"). "target" = the variable name (e.g. "foo_version").
- "out_of_scope": the version is inherited from OpenSearch core
  (e.g. ${{versions.X}}), set via System.getProperty, a sub-artifact the repo does
  not declare, or {coordinate} is not declared here at all. "target" empty.
- "none": {coordinate} is already at or above {patched_version} everywhere it is
  declared. "target" empty.

Return only the JSON object."""


def plan_edit(ctx, gradle_sources, mode="plugin"):
    """Return a validated edit plan dict, or ``None`` to fall back to the scanner.

    ``gradle_sources`` is the Gradle source to show the model (build.gradle blocks
    for ``mode='plugin'``, the version-catalog toml for ``mode='catalog'``).
    ``coordinate`` and ``patched_version`` are intentionally not part of the plan —
    the caller uses the verified values from ``ctx`` and re-verifies the named
    target exists. ``mode`` selects the prompt + the set of allowed actions.
    """
    template = _CATALOG_PROMPT if mode == "catalog" else _PROMPT
    prompt = template.format(
        coordinate=ctx["coordinate"],
        patched_version=ctx["patched_version"],
        installed_version=ctx.get("installed_version") or "unknown",
        gradle_sources=gradle_sources,
    )
    try:
        response = _runtime().invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        payload = json.loads(response["body"].read())
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        ).strip()
    except Exception as e:  # noqa: BLE001 — any Bedrock/parse failure -> fall back
        logger.warning("LLM planner call failed; falling back to scanner: %s", e)
        return None

    logger.info("LLM planner model=%s usage=%s raw_response=%s",
                MODEL_ID, payload.get("usage"), text)
    plan = _validate(text, mode)
    logger.info("LLM planner plan=%s", plan)
    return plan


def _validate(text, mode="plugin"):
    """Parse + schema-check the model output. Return a normalized plan or None.

    ``mode`` picks the allowed action set (plugin edits vs the catalog action)."""
    allowed = _ACTIONS.get(mode, _ACTIONS["plugin"])
    try:
        plan = json.loads(_strip_fences(text))
    except (ValueError, TypeError):
        logger.warning("LLM planner returned non-JSON output; falling back.")
        return None
    if not isinstance(plan, dict):
        return None

    action = plan.get("action")
    if action not in allowed:
        logger.warning("LLM planner returned unknown action %r; falling back.", action)
        return None

    target = plan.get("target")
    target = target.strip() if isinstance(target, str) else ""
    # edit/catalog actions must name what to edit; out_of_scope/none must not.
    if action in _TARGET_ACTIONS and not target:
        logger.warning("%s with no target; falling back.", action)
        return None
    if action not in _TARGET_ACTIONS and target:
        logger.warning("action %r must not name a target; falling back.", action)
        return None

    file = plan.get("file")
    file = file.strip() if isinstance(file, str) else ""
    reason = plan.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    return {"action": action, "file": file, "target": target, "reason": reason}


def _strip_fences(text):
    """Tolerate a ```json ... ``` wrapper if the model adds one."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        if t.startswith("json"):
            t = t[4:]
    return t.strip()
