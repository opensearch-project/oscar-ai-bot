# GitHub Agent

The GitHub agent gives OSCAR the ability to merge bot-generated PRs, transfer issues across repos, and bulk-comment on issues for the `opensearch-project` organization through Slack. It delegates GitHub API operations to the [GitHub MCP Server](https://github.com/github/github-mcp-server), a Go binary that runs as a subprocess inside the Lambda and communicates via the Model Context Protocol (MCP) over stdio.

## Architecture

```
User in Slack
    │
    ▼
Supervisor Agent → routes to GitHub-Specialist
    │
    ▼
Bedrock Agent (GitHub-Specialist)
    │
    ├─ githubReadOperations   (6 functions)
    └─ githubWriteOperations  (6 functions)
    │
    ▼
GitHub Lambda
    ├─ lambda_function.py   → Bedrock action group handler + param transforms
    ├─ mcp_client.py        → Subprocess lifecycle, token refresh, JSON-RPC
    ├─ github_api.py        → Direct REST API (transfer, comment, bulk-comment)
    ├─ authorizer.py        → Org validation + audit logging
    ├─ response_builder.py  → Bedrock response formatting
    └─ bin/github-mcp-server (Go binary, built in CI)
            │
            ├─ JSON-RPC 2.0 over stdio
            ├─ GitHub REST API (go-github)
            └─ GitHub GraphQL API (githubv4)
```

## Capabilities

### 1. Merge Bot-Generated PRs
Users request OSCAR to merge automated PRs (version bumps, release notes). The agent searches for the PR, verifies CI status, and merges after confirmation.

### 2. Transfer Issues
Move issues between `opensearch-project` repos. Target must be within the organization.

### 3. Bulk-Comment & Meta-Issues
Post the same comment across multiple issues at once, or create a tracking meta-issue linking to related sub-issues.

## Available Tools

### Read Operations (`githubReadOperations`)

| Function | MCP Tool | Description |
|----------|----------|-------------|
| `get_pr_details` | `pull_request_read` | PR details: title, state, author, reviewers, CI checks |
| `list_prs` | `list_pull_requests` | List PRs with state filtering |
| `get_issue_details` | `issue_read` | Issue details: title, state, assignees, labels |
| `list_issues` | `list_issues` | List issues with state/label filtering |
| `search_issues` | `search_issues` | Issue search with advanced syntax |
| `search_pull_requests` | `search_pull_requests` | PR search with advanced syntax |

### Write Operations (`githubWriteOperations`)

| Function | Route | Description |
|----------|-------|-------------|
| `merge_pr` | MCP (`merge_pull_request`) | Merge a PR (merge/squash/rebase) |
| `transfer_issue` | Direct API | Transfer issue to another repo within org |
| `create_issue` | MCP (`issue_write`) | Create an issue with labels and assignees |
| `close_issue` | MCP (`issue_write`) | Close an issue with reason |
| `add_comment` | Direct API | Comment on a single issue or PR |
| `bulk_comment` | Direct API | Comment on multiple issues/PRs at once |

All write operations require explicit user confirmation before execution.

## Direct GitHub API Calls

Three operations bypass the MCP server and call the GitHub REST API directly via `github_api.py`:

| Function | API Endpoint | Why not MCP |
|----------|-------------|-------------|
| `transfer_issue` | `POST /repos/{owner}/{repo}/issues/{issue_number}/transfer` | Not implemented in the MCP server |
| `add_comment` | `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` | Simpler than MCP for single comments |
| `bulk_comment` | `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` (per issue) | Not a native MCP operation |

These calls reuse the installation token from `MCPClient.get_token()` and include the same retry/rate-limit logic.

## How It Works

1. **Binary Bundling** — The `github-mcp-server` Go binary is cross-compiled for `linux/amd64` during CI (or locally via `scripts/build-github-mcp-server.sh`) and placed in `agents/github/lambda/bin/`. CDK's `PythonFunction` includes it in the Lambda zip automatically.

2. **Cold Start** — On the first Lambda invocation, the binary is copied to `/tmp/`, an installation token is generated, the subprocess is spawned, and an MCP handshake is performed.

3. **Warm Invocations** — The subprocess persists as a global singleton. No restart unless the token is nearing expiry.

4. **Token Refresh** — Installation tokens expire after 1 hour. The client checks before each call and restarts the subprocess with a fresh token if needed.

## Building the MCP Server Binary

### CI (automatic)

Both `deploy-beta.yml` and `deploy-prod.yml` automatically build the binary. No manual step needed.

### Local development

```bash
./scripts/build-github-mcp-server.sh
```

Requires Go 1.24+. Binary is written to `agents/github/lambda/bin/github-mcp-server` (gitignored).

## GitHub App Credentials Setup

The agent authenticates with GitHub using a GitHub App. Credentials are stored in AWS Secrets Manager.

### 1. Create a GitHub App

1. Go to GitHub → Settings → Developer settings → GitHub Apps → New GitHub App.
2. Set permissions:
   - **Repository permissions**: Contents (write), Issues (write), Pull requests (write), Metadata (read)
3. Install the App on the `opensearch-project` organization.
4. Note the **App ID**, **Installation ID**, and generate a **private key**.

### 2. Store credentials in Secrets Manager

The CDK stack creates a secret named `oscar-github-env-{env}`.

```bash
aws secretsmanager put-secret-value \
  --secret-id oscar-github-env-dev \
  --secret-string '{
    "GITHUB_APP_ID": "123456",
    "GITHUB_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----",
    "GITHUB_INSTALLATION_ID": "78901234"
  }'
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MCP_TOOLSETS` | Comma-separated MCP toolsets to enable | `issues,pull_requests` |
| `MCP_READ_ONLY` | Restrict to read-only tools (`true`/`false`) | `false` |
| `GITHUB_SECRET_NAME` | Secrets Manager secret name (set by CDK) | — |

## Security

- **Organization scope** — All operations are enforced to target `opensearch-project` only.
- **Privileged access** — Only available to users in `FULLY_AUTHORIZED_USERS`.
- **Confirmation required** — All write operations require explicit user confirmation.
- **Token lifecycle** — Installation tokens are short-lived (~1 hour) and never logged.
- **Audit logging** — All operations are logged with request ID, function name, and repo.
