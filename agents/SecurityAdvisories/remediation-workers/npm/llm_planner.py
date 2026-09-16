# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""LLM edit-planner for the npm remediation worker.

Given the CVE inputs and the repo's ``package.json``, ask a Bedrock model *how*
to bump the vulnerable package — i.e. which of the deterministic edit strategies
to apply. The model returns a small JSON "plan"; it never emits file contents
(the deterministic code applies the edit and regenerates the lockfile).

Deliberately narrow scope so the model can't hallucinate the important values:
  - the package name and target version come from ``ctx`` (verified upstream by
    the SecurityAdvisories pre-flight via the GitHub Advisory API), NOT the model;
  - the model only chooses the routing ``action`` (and, for edits, which
    ``sections`` of package.json to touch);
  - the output is validated against a fixed schema before use.

On any failure (Bedrock error, empty/invalid output, schema violation) this
returns ``None`` so the caller falls back to the deterministic router — the same
pattern as ``narrative_generator._rule_based_fallback``.
"""

import json
import logging
import os

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Cross-region inference profile ("us." prefix). Overridable so the model can be
# bumped without a code change; default matches what OSCAR already runs elsewhere.
MODEL_ID = os.environ.get(
    "REMEDIATION_LLM_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
MAX_TOKENS = 512
TEMPERATURE = 0  # deterministic-as-possible: this is a routing decision, not prose

# package.json sections the model may target, and the routing actions it may pick.
_ALLOWED_SECTIONS = ("dependencies", "devDependencies", "resolutions")
_ALLOWED_ACTIONS = ("upgrade_dep", "edit_and_install", "add_resolution", "none")

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
    "You route npm/yarn CVE fixes. Given a package.json and a target package + "
    "patched version, decide HOW to apply the bump. Reply with ONLY a JSON object, "
    "no markdown or prose."
)

_PROMPT = """\
Target package: {package}
Target version (already verified — do not change it): {patched_version}
Currently installed: {installed_version}
Appears in yarn.lock (a resolved transitive dependency): {in_lockfile}

package.json dependency sections (dependencies / devDependencies / resolutions):
{package_json}

Choose exactly one action and return JSON of the form:
{{"action": "<action>", "sections": ["<section>", ...],
  "reason": "<one short sentence: where {package} is declared and why this action>"}}

Actions:
- "upgrade_dep": {package} is a direct dependency (in "dependencies" or
  "devDependencies") with NO "resolutions" entry. Bump it directly.
  "sections" must be empty.
- "edit_and_install": {package} is declared in "resolutions" (optionally also a
  direct dep). Edit the version everywhere it is declared. "sections" lists every
  section it appears in.
- "add_resolution": {package} is NOT declared in package.json but IS in yarn.lock
  (an undeclared transitive). Add a "resolutions" entry. "sections" must be empty.
- "none": {package} is already at or above {patched_version} everywhere it is
  declared; no change is needed. "sections" must be empty.

Return only the JSON object."""


def plan_edit(ctx, package_json_text, in_lockfile):
    """Return a validated edit plan dict, or ``None`` to fall back to the router.

    Plan shape: ``{"action": <one of _ALLOWED_ACTIONS>, "sections": [<sections>]}``.
    ``package`` and ``patched_version`` are intentionally not part of the plan —
    the caller uses the verified values from ``ctx``.
    """
    prompt = _PROMPT.format(
        package=ctx["package_name"],
        patched_version=ctx["patched_version"],
        installed_version=ctx.get("installed_version") or "unknown",
        in_lockfile=bool(in_lockfile),
        package_json=package_json_text,
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
        logger.warning("LLM planner call failed; falling back to router: %s", e)
        return None

    logger.info("LLM planner model=%s usage=%s raw_response=%s",
                MODEL_ID, payload.get("usage"), text)
    plan = _validate(text)
    logger.info("LLM planner plan=%s", plan)
    return plan


def _validate(text):
    """Parse + schema-check the model output. Return a normalized plan or None."""
    try:
        plan = json.loads(_strip_fences(text))
    except (ValueError, TypeError):
        logger.warning("LLM planner returned non-JSON output; falling back.")
        return None
    if not isinstance(plan, dict):
        return None

    action = plan.get("action")
    if action not in _ALLOWED_ACTIONS:
        logger.warning("LLM planner returned unknown action %r; falling back.", action)
        return None

    sections = plan.get("sections") or []
    if not isinstance(sections, list) or any(s not in _ALLOWED_SECTIONS for s in sections):
        logger.warning("LLM planner returned invalid sections %r; falling back.", sections)
        return None
    # edit_and_install must name at least one section; the others take none.
    if action == "edit_and_install" and not sections:
        logger.warning("edit_and_install with no sections; falling back.")
        return None
    if action != "edit_and_install" and sections:
        logger.warning("action %r must not name sections; falling back.", action)
        return None

    reason = plan.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    return {"action": action, "sections": sections, "reason": reason}


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
