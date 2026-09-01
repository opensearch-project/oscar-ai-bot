# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Ecosystem-agnostic CVE remediation flow (container Lambda).

Everything that is the SAME for every ecosystem lives here: clone the repo,
commit the changed files, push to the bot fork, and open a pull request via the
GitHub CLI. The ecosystem-specific part — which manifest to edit and how to
regenerate the lockfile — is supplied by a ``strategy`` module (see ``npm.py``).

Unlike the SecurityAdvisories agent Lambda, this Lambda is NOT a Bedrock action
group. It is invoked Lambda-to-Lambda by the SecurityAdvisories remediation
handler's ``dispatch`` step with a plain event dict, and returns a plain result
dict (no Bedrock envelope):

    event  = {repo_name, cve_id, package, patched_version, installed_version,
              base_branch?}
    result = {status, pr_url?, changed_files?, message, ...}

Write target: fixes are pushed to a FORK (never a branch on the live org repo),
with the PR opened against that fork. The fork owner is ``REMEDIATION_WRITE_OWNER``
(dev: a personal fork; prod: the bot fork). The affected upstream repo name is
passed in ``repo_name``; the fork carries the same name.
"""

import logging
import os
import shutil
import subprocess
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Commit author/committer identity. OpenSearch repos enforce DCO, so we always
# commit with -s; git derives the Signed-off-by trailer from these, which DCO
# requires to match the author. Overridable via env so prod can set the real bot
# account (e.g. opensearch-ci-bot or the Oscar GitHub App) — matching the push
# token — without a code change; dev uses the placeholder below.
GIT_USER_NAME = os.environ.get("REMEDIATION_GIT_NAME", "OSCAR AI Bot")
GIT_USER_EMAIL = os.environ.get(
    "REMEDIATION_GIT_EMAIL", "oscar-ai-bot@users.noreply.github.com"
)

WORK_DIR = "/tmp/repo"

# Owner of the fork we push to and open the PR against. Never the live org repo.
WRITE_OWNER = os.environ.get("REMEDIATION_WRITE_OWNER", "")


class RemediationError(Exception):
    """Raised when the remediation cannot be completed."""


def handle(event, strategy):
    """Run the remediation, then post the outcome to the originating Slack thread.

    Dispatch from the SecurityAdvisories agent is fire-and-forget (the agent turn
    ends before this finishes), so the user learns the result from a message this
    worker posts back into the Slack thread (``slack_channel`` + ``slack_thread_ts``
    carried in the event). When there's no thread context (invoked outside Slack),
    it just logs. The result dict is still returned for logs/tests.
    """
    result = _execute(event, strategy)
    _notify_slack(event, result)
    return result


def _execute(event, strategy):
    """Run the full remediation for the given ecosystem ``strategy``.

    Returns a plain result dict (the caller relays it); never raises for an
    expected failure — those become ``{"status": "error"|..., "message": ...}``.
    """
    token = _resolve_token()
    if not token:
        return {"status": "error",
                "message": "GitHub credentials are not configured."}
    if not WRITE_OWNER:
        return {"status": "error",
                "message": "REMEDIATION_WRITE_OWNER is not configured."}

    try:
        ctx = strategy.build_context(event, WRITE_OWNER)
    except RemediationError as e:
        return {"status": "error", "message": str(e)}

    try:
        _clone(WORK_DIR, ctx["write_owner"], ctx["repo_name"],
               token=token, base_branch=ctx["base_branch"],
               sparse_paths=getattr(strategy, "sparse_paths", None))

        # --- ecosystem-specific: edit manifest + regenerate the lockfile -----
        strategy.apply_fix(WORK_DIR, ctx)
        strategy.regenerate(WORK_DIR, ctx)

        changed = _changed_files(WORK_DIR)
        if not changed:
            # The manifest already satisfies the patched version (e.g. a fix
            # merged since the scan). Nothing to open a PR for.
            return {
                "status": "no_change",
                "cve_id": ctx["cve_id"],
                "message": (
                    f"{ctx['repo_name']} already satisfies {ctx['package_name']} "
                    f">= {ctx['patched_version']}; no change needed."
                ),
            }
        logger.info("Changed files: %s", changed)

        pr_url = _commit_and_open_pr(WORK_DIR, ctx, token)
    except RemediationError as e:
        return {"status": "error", "cve_id": ctx.get("cve_id"), "message": str(e)}

    return {
        "status": "success",
        "ecosystem": strategy.name,
        "cve_id": ctx["cve_id"],
        "repository": f"{ctx['write_owner']}/{ctx['repo_name']}",
        "pr_url": pr_url,
        "changed_files": changed,
        "message": strategy.summary(ctx),
    }


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

def _resolve_token():
    """GitHub token from the environment, else from Secrets Manager.

    Dev uses a ``GH_TOKEN`` env var (a personal PAT). Prod stores the bot
    credential in Secrets Manager named by ``GH_TOKEN_SECRET_NAME``.
    """
    token = os.environ.get("GH_TOKEN")
    if token:
        return token

    secret_name = os.environ.get("GH_TOKEN_SECRET_NAME")
    if not secret_name:
        return ""
    try:
        import boto3
        client = boto3.client("secretsmanager")
        value = client.get_secret_value(SecretId=secret_name)["SecretString"]
        # The secret may be the raw token or a JSON blob with a "token" field.
        value = value.strip()
        if value.startswith("{"):
            import json
            return (json.loads(value).get("token") or "").strip()
        return value
    except Exception as e:  # noqa: BLE001 — never leak the underlying error
        logger.error("Failed to read GitHub token from Secrets Manager: %s", e)
        return ""


# --------------------------------------------------------------------------
# Slack result notification (async worker replies in the originating thread)
# --------------------------------------------------------------------------

def _notify_slack(event, result):
    """Post the remediation outcome back into the originating Slack thread.

    No-ops (logs only) when there's no thread context (invoked outside Slack) or
    no Slack token configured. Never raises — a failed notification must not turn
    a successful remediation into an error.
    """
    channel = (event.get("slack_channel") or "").strip()
    thread_ts = (event.get("slack_thread_ts") or "").strip()
    if not (channel and thread_ts):
        logger.info("No Slack thread context on the event; skipping thread reply.")
        return

    token = _resolve_slack_token()
    if not token:
        logger.warning("No Slack token configured; cannot post result to thread.")
        return

    try:
        _post_slack_message(token, channel, thread_ts, _format_slack_message(result))
        logger.info("Posted remediation result to Slack thread %s/%s", channel, thread_ts)
    except Exception as e:  # noqa: BLE001 — notification failure must not fail the run
        logger.error("Failed to post remediation result to Slack: %s", e)


def _format_slack_message(result):
    """Human-readable Slack message for a remediation result dict."""
    status = result.get("status")
    cve = result.get("cve_id") or "the CVE"
    if status == "success":
        return (
            f":white_check_mark: Opened a pull request for *{cve}*"
            + (f": {result['pr_url']}" if result.get("pr_url") else ".")
        )
    if status == "no_change":
        return f":information_source: *{cve}*: {result.get('message', 'no change needed.')}"
    return f":x: Remediation for *{cve}* failed: {result.get('message', 'unknown error.')}"


def _resolve_slack_token():
    """Slack bot token from the environment, else from Secrets Manager.

    Mirrors ``_resolve_token`` for GitHub: dev can set ``SLACK_BOT_TOKEN``; prod
    stores it in Secrets Manager named by ``SLACK_BOT_TOKEN_SECRET_NAME`` (raw
    token or a JSON blob with a ``token`` field).
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    if token:
        return token

    secret_name = os.environ.get("SLACK_BOT_TOKEN_SECRET_NAME")
    if not secret_name:
        return ""
    try:
        import boto3
        client = boto3.client("secretsmanager")
        value = client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        if value.startswith("{"):
            import json
            return (json.loads(value).get("token") or "").strip()
        return value
    except Exception as e:  # noqa: BLE001 — never leak the underlying error
        logger.error("Failed to read Slack token from Secrets Manager: %s", e)
        return ""


def _post_slack_message(token, channel, thread_ts, text):
    """POST chat.postMessage to reply in a thread (stdlib only, no requests dep)."""
    import json
    import urllib.request

    body = json.dumps({
        "channel": channel,
        "thread_ts": thread_ts,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read() or b"{}")
    if not payload.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage failed: {payload.get('error')}")


# --------------------------------------------------------------------------
# Shared git / GitHub steps
# --------------------------------------------------------------------------

def _clone(work_dir, owner, repo_name, token, base_branch="main", sparse_paths=None):
    """Shallow-clone ``owner/repo_name`` at ``base_branch`` into ``work_dir``.

    Authenticates the clone so it works on a private fork and so the later push
    reuses the same credentials. ``sparse_paths`` (for huge repos like core) does
    a blobless sparse checkout; npm repos clone normally.
    """
    # Lambda reuses /tmp across warm invocations — remove any prior checkout.
    shutil.rmtree(work_dir, ignore_errors=True)
    url = f"https://x-access-token:{token}@github.com/{owner}/{repo_name}.git"

    if sparse_paths:
        _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
              "--branch", base_branch, url, work_dir], "git clone (sparse)",
             redact=token)
        _run(["git", "-C", work_dir, "sparse-checkout", "set", "--no-cone",
              *sparse_paths], "git sparse-checkout set")
    else:
        logger.info("Cloning %s/%s (%s) ...", owner, repo_name, base_branch)
        _run(["git", "clone", "--depth", "1", "--branch", base_branch, url,
              work_dir], "git clone", redact=token)


def _commit_and_open_pr(work_dir, ctx, token):
    """Create a branch, commit the changed files, push to the fork, open a PR."""
    owner, repo_name = ctx["write_owner"], ctx["repo_name"]
    branch_name, base_branch = ctx["branch_name"], ctx["base_branch"]
    remote = f"https://x-access-token:{token}@github.com/{owner}/{repo_name}.git"

    _run(["git", "-C", work_dir, "config", "user.name", GIT_USER_NAME],
         "git config name")
    _run(["git", "-C", work_dir, "config", "user.email", GIT_USER_EMAIL],
         "git config email")
    _run(["git", "-C", work_dir, "checkout", "-b", branch_name],
         "git checkout -b")
    # -A stages adds, modifications AND deletions.
    _run(["git", "-C", work_dir, "add", "-A"], "git add")
    # -s adds the Signed-off-by trailer (from user.name/user.email above) that
    # OpenSearch's DCO check requires on every commit.
    _run(["git", "-C", work_dir, "commit", "-s", "-m", ctx["commit_message"]],
         "git commit")
    _run(["git", "-C", work_dir, "push", remote,
          f"HEAD:refs/heads/{branch_name}"], "git push", redact=token)

    # PR is opened WITHIN the fork (base = the fork's base_branch), so we never
    # open a pull request on the live upstream repo.
    env = {**os.environ, "GH_TOKEN": token}
    result = subprocess.run(
        ["gh", "pr", "create",
         "--repo", f"{owner}/{repo_name}",
         "--base", base_branch,
         "--head", branch_name,
         "--title", ctx["pr_title"],
         "--body", ctx["pr_body"]],
        cwd=work_dir, capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        logger.error("gh pr create failed: %s", result.stderr[-500:])
        raise RemediationError(f"gh pr create failed: {result.stderr[-300:]}")
    return result.stdout.strip()


def _changed_files(work_dir):
    """Repo-relative paths added/modified/deleted in the working tree."""
    _run(["git", "-C", work_dir, "add", "-A"], "git add -A")
    result = subprocess.run(
        ["git", "-C", work_dir, "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run(cmd, label, redact=None):
    """Run a subprocess, raising RemediationError on failure (token-safe logs)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr[-300:]
        if redact:
            err = err.replace(redact, "***")
        raise RemediationError(f"{label} failed: {err}")
    return result


def new_branch_name(cve_id, package_name):
    """A collision-resistant branch name (CVE in the branch is allowed)."""
    slug = "".join(c if c.isalnum() else "-" for c in package_name.lower()).strip("-")
    return f"oscar/{cve_id.lower()}-{slug}-{uuid.uuid4().hex[:8]}"
