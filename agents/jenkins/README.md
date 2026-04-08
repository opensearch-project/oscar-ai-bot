# Jenkins Agent

The Jenkins agent gives OSCAR the ability to list, inspect, and trigger Jenkins jobs through Slack. It auto-discovers jobs by parsing Jenkinsfiles directly from the GitHub repository, making the Jenkinsfiles the single source of truth for job names, parameters, and descriptions.

## How It Works

1. **Discovery** — At Lambda cold start, the agent fetches all `*.jenkinsfile` files under the `jenkins/` directory of the configured GitHub repository using the GitHub API.
2. **Parsing** — Each file is parsed for a `parameters {}` block. The parser extracts parameter names, types, descriptions, defaults, and choices.
3. **Filtering** — Only files with a `@job-name` annotation are registered. Files without it are silently skipped. Files in the ignore list are skipped entirely.
4. **Caching** — The parsed job registry is cached in memory for 1 hour (configurable). Warm Lambda invocations reuse the cache.
5. **Execution** — When a user triggers a job, the agent validates parameters against the parsed definitions and calls the Jenkins REST API.

## Onboarding a New Jenkins Job

To make a Jenkins job available through OSCAR:

### 1. Add annotations to the Jenkinsfile

Add two comment lines after the license header in your Jenkinsfile:

```groovy
// @job-name: my-job-name
// @description: Short description of what this job does
```

- `@job-name` must match the Jenkins job name exactly (as it appears in the Jenkins URL).
- `@description` is shown to users when they run `get_job_info` or `list_jobs`.

### 2. Mark parameters as Required or Optional

In each parameter's `description` field, prefix with `<Required>` or `<Optional>`:

```groovy
parameters {
    string(
        name: 'RELEASE_VERSION',
        description: '<Required> Release version, e.g. 2.19.0',
        trim: true
    )
    string(
        name: 'COMPONENT_NAME',
        description: '<Optional> Specific component to build, or leave empty for all',
        trim: true
    )
    booleanParam(
        name: 'DRY_RUN',
        defaultValue: false,
        description: '<Optional> Run without making changes'
    )
}
```

**Required/Optional detection rules (in priority order):**

1. Description starts with `Conditionally-Required` or `<Conditionally-Required>` → treated as optional (the description explains when it's needed, Jenkins validates server-side)
2. Description starts with `Required` or `<Required>` → required
3. Description starts with `Optional` or `<Optional>` → optional
4. Has a `defaultValue` → optional
5. No indicator and no default → required (conservative)

Use `<Conditionally-Required>` for "either A or B" scenarios:
```groovy
string(
    name: 'BUNDLE_MANIFEST_URL',
    description: '<Conditionally-Required> Either this or DISTRIBUTION_URL must be provided.',
    trim: true
)
```

### 3. Deploy OSCAR

No code changes needed in OSCAR. Just deploy and the new job will be auto-discovered on the next Lambda cold start.

## Environment Variables

### Required

These must be set before `cdk deploy`. Set them in your `.env` file or export in your shell.

| Variable | Description | Default |
|----------|-------------|---------|
| `JENKINS_URL` | Jenkins server URL | `https://build.ci.opensearch.org` |
| `JENKINSFILE_GITHUB_REPO` | GitHub repo in `owner/repo` format (not the full URL) | `opensearch-project/opensearch-build` |
| `JENKINSFILE_GITHUB_BRANCH` | Branch to fetch Jenkinsfiles from | `main` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `JENKINS_VERIFY_SSL` | Verify SSL certificates for Jenkins API calls (`true`/`false`) | `true` |
| `JENKINSFILE_IGNORE_LIST` | Comma-separated Jenkinsfile paths to skip during discovery | (empty) |

**Example 
Add it in `.env`**

```
JENKINS_URL=https://your-jenkins-url
JENKINSFILE_GITHUB_REPO=you-user-name/your-repo
JENKINSFILE_GITHUB_BRANCH=main
JENKINS_VERIFY_SSL=true
JENKINSFILE_IGNORE_LIST=jenkins/opensearch/benchmark-test.jenkinsfile,jenkins/opensearch/benchmark-pull-request.jenkinsfile
```

OR use export key=value: export JENKINS_VERIFY_SSL=true

## Jenkins API Token Setup

The agent authenticates with Jenkins using an API token stored in AWS Secrets Manager.

### 1. Generate an API token in Jenkins

1. Log in to Jenkins at your `JENKINS_URL`.
2. Click your username (top right) → **Configure**.
3. Click Security on left, and click on **Add new Token**.
4. Give it a name and click **Generate**.
5. Copy the token — it won't be shown again.

### 2. Store the token in Secrets Manager

The CDK stack creates a secret named `oscar-jenkins-api-token-{env}` (e.g., `oscar-jenkins-api-token-dev`).

After deployment, populate it with a JSON value containing both the Jenkins API token and a GitHub token:

```bash
aws secretsmanager put-secret-value \
  --secret-id oscar-jenkins-api-token-dev \
  --secret-string '{"jenkins_api_token": "your-username:your-api-token", "github_token": "ghp_your_github_token"}'
```

The Lambda reads this secret at startup via the `JENKINS_SECRET_NAME` environment variable (automatically set by CDK).

### Secret format

```json
{
  "jenkins_api_token": "username:api-token",
  "github_token": "ghp_xxxxxxxxxxxx"
}
```

| Key | Description | Required |
|-----|-------------|----------|
| `jenkins_api_token` | Jenkins credentials in `username:token` format | Yes |
| `github_token` | GitHub personal access token for Jenkinsfile discovery | No (but strongly recommended — unauthenticated GitHub API is limited to 60 requests/hour) |

### GitHub token setup

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Create a token with **read-only** access to the `Contents` permission on the target repository.
3. Add it to the secret JSON as `github_token`.

### Permissions

The Jenkins user associated with this token needs permission to:
- View and trigger the jobs you want OSCAR to execute
- Read the build queue and build results

## Security: Two-Phase Execution

All job executions follow a mandatory two-phase workflow:

1. **Inform** — The agent calls `get_job_info`, presents job details, and asks the user to confirm.
2. **Execute** — Only after explicit user confirmation, the agent calls `trigger_job` with `confirmed=true`.

The agent will never execute a job without user confirmation. This is enforced both in the agent instructions and in the Lambda handler (the `confirmed` parameter is checked server-side).

## Architecture

```
User in Slack
    │
    ▼
Supervisor Agent → routes to Jenkins-Specialist
    │
    ▼
Bedrock Agent (Jenkins-Specialist)
    │
    ├─ get_job_info() ──▶ Returns parsed Jenkinsfile data
    ├─ list_jobs()     ──▶ Returns all discovered jobs
    └─ trigger_job()   ──▶ Jenkins REST API
    │
    ▼
Jenkins Lambda
    ├─ jenkinsfile_fetcher.py  → Fetches from GitHub, caches registry
    ├─ jenkinsfile_parser.py   → Parses Groovy parameter blocks
    ├─ job_definitions.py      → JobRegistry + validation
    ├─ jenkins_client.py       → REST API calls to Jenkins
    ├─ config.py               → URL, SSL, timeouts, secrets
    └─ lambda_function.py      → Bedrock action group handler
```
