# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Ecosystem-agnostic CVE remediation flow (ECS Fargate worker).

Everything that is the SAME for every ecosystem lives here: clone the repo,
commit the changed files, push the fix branch to the bot fork, and open a pull
request via the GitHub CLI. The ecosystem-specific part — which manifest to edit
and how to regenerate the lockfile — is supplied by a ``strategy`` module (see
``npm.py``).

This runs as a Fargate task, launched by the SecurityAdvisories remediation
handler's dispatch step (ecs.run_task). The payload arrives as environment
variables (see ``main.py``, the entrypoint); this module works from a plain
event dict and returns a plain result dict:

    event  = {repo_name, cve_id, package, patched_version, installed_version,
              base_branch?, slack_channel?, slack_thread_ts?}
    result = {status, pr_url?, changed_files?, message, ...}

Repo owners (both required): ``REMEDIATION_BASE_OWNER`` is the repo we clone from
and open the PR against; ``REMEDIATION_WRITE_OWNER`` is the fork we push the fix
branch to. Dev sets both to a personal fork (clone the fork, PR within it); prod
sets BASE_OWNER to the upstream org and WRITE_OWNER to the bot fork, so the fix
never depends on the fork being in sync with upstream. We never push a branch to
the live upstream repo — only the PR is opened there.
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

# WRITE_OWNER: the fork we push the fix branch to. BASE_OWNER: the repo we clone
# from and open the PR against. Dev sets both to the personal fork (clone the
# fork, PR within it). Prod sets BASE_OWNER to the upstream org (clone the
# current upstream, PR to upstream) and WRITE_OWNER to the bot's fork — so the
# fork's staleness never affects the fix.
WRITE_OWNER = os.environ.get("REMEDIATION_WRITE_OWNER", "")
BASE_OWNER = os.environ.get("REMEDIATION_BASE_OWNER", "")

# Per-subprocess timeouts (seconds). Fargate has no max task duration, so a hung
# git or gh command would run (and bill) indefinitely — bound each so a stuck
# command fails fast into a RemediationError. git clone of a large repo is the
# slow case; gh pr create is a quick API call. (yarn has its own longer timeout
# in the strategy, since installs are the long pole.)
GIT_TIMEOUT = 300
GH_TIMEOUT = 120


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
    if not BASE_OWNER:
        return {"status": "error",
                "message": "REMEDIATION_BASE_OWNER is not configured."}

    try:
        ctx = strategy.build_context(event, WRITE_OWNER, BASE_OWNER)
    except RemediationError as e:
        return {"status": "error", "message": str(e)}

    try:
        # Clone from BASE_OWNER (upstream in prod, the fork in dev) so the fix is
        # computed against current state, independent of the fork's sync status.
        _clone(WORK_DIR, ctx["base_owner"], ctx["repo_name"],
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
        logger.error("Remediation failed for %s: %s", ctx.get("cve_id"), e)
        return {"status": "error", "cve_id": ctx.get("cve_id"), "message": str(e)}

    return {
        "status": "success",
        "ecosystem": strategy.name,
        "cve_id": ctx["cve_id"],
        "repository": f"{ctx['base_owner']}/{ctx['repo_name']}",
        "pr_url": pr_url,
        "changed_files": changed,
        "message": strategy.summary(ctx),
    }


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

def _resolve_token():
    """GitHub token from Secrets Manager, named by ``GH_TOKEN_SECRET_NAME``.

    Secrets Manager only — no raw-token env var, which would be stored in
    plaintext in the task definition. The value may be the raw token or a JSON
    blob with a ``token`` field.
    """
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
    """Slack bot token from Secrets Manager, named by ``SLACK_BOT_TOKEN_SECRET_NAME``.

    Secrets Manager only (mirrors ``_resolve_token``) — no raw-token env var. The
    value may be the raw token or a JSON blob with a ``token`` field.
    """
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

# Askpass helper shipped alongside this module (see Dockerfile). git calls it for
# the HTTPS password so the token stays out of the URL/argv/.git/config.
_ASKPASS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "git-askpass.sh")


def _git_env(token):
    """Environment for git network ops: token supplied via GIT_ASKPASS, not the URL.

    The URL carries only the (non-secret) ``x-access-token`` username; git asks
    GIT_ASKPASS for the password, which reads GH_TOKEN from here. GIT_TERMINAL_PROMPT=0
    makes git fail fast rather than hang if the credential can't be supplied.
    """
    return {
        **os.environ,
        "GH_TOKEN": token,
        "GIT_ASKPASS": _ASKPASS,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _clone(work_dir, owner, repo_name, token, base_branch="main", sparse_paths=None):
    """Shallow-clone ``owner/repo_name`` at ``base_branch`` into ``work_dir``.

    Authenticates via GIT_ASKPASS so the same credential mechanism covers both
    the clone and the later push (the fork is public, so the clone itself needs
    no auth). ``sparse_paths`` (for huge repos like core) does a blobless sparse
    checkout; npm repos clone normally.
    """
    # Lambda reuses /tmp across warm invocations — remove any prior checkout.
    shutil.rmtree(work_dir, ignore_errors=True)
    url = f"https://x-access-token@github.com/{owner}/{repo_name}.git"
    env = _git_env(token)

    if sparse_paths:
        _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
              "--branch", base_branch, url, work_dir], "git clone (sparse)", env=env)
        _run(["git", "-C", work_dir, "sparse-checkout", "set", "--no-cone",
              *sparse_paths], "git sparse-checkout set")
    else:
        logger.info("Cloning %s/%s (%s) ...", owner, repo_name, base_branch)
        _run(["git", "clone", "--depth", "1", "--branch", base_branch, url,
              work_dir], "git clone", env=env)


def _commit_and_open_pr(work_dir, ctx, token):
    """Create a branch, commit the changed files, push to the fork, open a PR."""
    write_owner, base_owner = ctx["write_owner"], ctx["base_owner"]
    repo_name = ctx["repo_name"]
    branch_name, base_branch = ctx["branch_name"], ctx["base_branch"]
    # Push the fix branch to the WRITE_OWNER fork (token via GIT_ASKPASS, not the
    # URL — only the non-secret username appears here).
    remote = f"https://x-access-token@github.com/{write_owner}/{repo_name}.git"
    env = _git_env(token)

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
          f"HEAD:refs/heads/{branch_name}"], "git push", env=env)

    # Open the PR on the BASE_OWNER repo. The head is owner-qualified so this
    # works both cross-fork (prod: WRITE_OWNER fork -> upstream) and same-repo
    # (dev: base_owner == write_owner, i.e. a PR within the fork). gh reads
    # GH_TOKEN from env.
    try:
        result = subprocess.run(
            ["gh", "pr", "create",
             "--repo", f"{base_owner}/{repo_name}",
             "--base", base_branch,
             "--head", f"{write_owner}:{branch_name}",
             "--title", ctx["pr_title"],
             "--body", ctx["pr_body"]],
            cwd=work_dir, capture_output=True, text=True, env=env,
            timeout=GH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RemediationError(f"gh pr create timed out after {GH_TIMEOUT}s")
    if result.returncode != 0:
        logger.error("gh pr create failed: %s", result.stderr[-500:])
        raise RemediationError(f"gh pr create failed: {result.stderr[-300:]}")
    return result.stdout.strip()


def _changed_files(work_dir):
    """Repo-relative paths added/modified/deleted in the working tree."""
    _run(["git", "-C", work_dir, "add", "-A"], "git add -A")
    result = _run(["git", "-C", work_dir, "diff", "--cached", "--name-only"],
                  "git diff")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run(cmd, label, env=None, timeout=GIT_TIMEOUT):
    """Run a subprocess, raising RemediationError on failure or timeout.

    ``env`` is passed through for git network ops that need GIT_ASKPASS/GH_TOKEN.
    The token is never on the command line (it's supplied via GIT_ASKPASS), so
    there's nothing to redact from the captured stderr. ``timeout`` bounds a hung
    command (Fargate won't stop it on its own).
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RemediationError(f"{label} timed out after {timeout}s")
    if result.returncode != 0:
        raise RemediationError(f"{label} failed: {result.stderr[-300:]}")
    return result


def new_branch_name(cve_id, package_name):
    """A collision-resistant branch name (CVE in the branch is allowed)."""
    slug = "".join(c if c.isalnum() else "-" for c in package_name.lower()).strip("-")
    return f"oscar/{cve_id.lower()}-{slug}-{uuid.uuid4().hex[:8]}"
