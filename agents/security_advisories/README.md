# Security Advisories Agent

The Security Advisories agent gives OSCAR the ability to query CVEs and security vulnerabilities affecting OpenSearch project components through Slack. It connects to a cross-account OpenSearch cluster via STS AssumeRole and AWS SigV4 authentication, using direct DSL query construction to retrieve vulnerability scan data.

## Architecture

```
User in Slack
    │
    ▼
Supervisor Agent
    │
    ▼
Security Advisories Agent
    │
    ▼
Security Advisories Lambda
    ├─ Projects Handler (aggregation-based project/tag discovery)
    ├─ DSL Query Builder (constructs bool/filter queries from structured parameters)
    │       │
    │       ▼
    │   OpenSearch Cluster
    │       └─ Returns hits from scans index
    │       │
    ├─ Response Filter (severity, exclusion, age filtering)
    └─ Summary Builder (severity count aggregation)
```

## How It Works

1. **Cross-Account Access** — The Lambda assumes a role in the OpenSearch account using STS, then signs requests with SigV4.
2. **DSL Query Construction** — The version and project name parameters (if provided) are used to construct a bool/filter query directly. Version strings are resolved to canonical tag format via `resolve_version_tag()`, and the query targets the latest scans index.
3. **Query Execution** — The DSL query is sent to the scans index via `opensearch_request()` with SigV4 authentication.
4. **Post-Query Filtering** — Results are filtered by severity level, exclusion status, and scan age at the application layer (these array-level filters can't be efficiently done in OpenSearch DSL).

**Project Discovery** — The `list_projects` function uses terms aggregations to enumerate available projects and their tags without querying scan documents. This is especially useful when queries reference relative terms like "latest release" or "most recent version" — the agent calls `list_projects` first to resolve the concrete version before querying vulnerabilities.

## Bedrock Functions

| Function | Description |
|----------|-------------|
| `query_vulnerabilities` | Query CVEs using direct DSL construction scoped by version and/or project name |
| `list_projects` | List available components and their tags/versions |

### query_vulnerabilities

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Natural language query about vulnerabilities (e.g., "Show me critical CVEs for OpenSearch Dashboards 2.19.6") |
| `version` | No | Version to scope the query (e.g., "2.19.6", "3.0.0") |
| `project_name` | No | Project name to scope the query (e.g., "OpenSearch Dashboards", "OpenSearch") |
| `severity` | No | Comma-separated severity filter (e.g., "CRITICAL", "CRITICAL,HIGH"). Valid: CRITICAL, HIGH, MEDIUM, LOW |
| `age_days` | No | Maximum age in days for scan results (e.g., 30 for the past month) |

### list_projects

No parameters. Returns all projects and their available tags sorted alphabetically.

## Data Model

Scan results are stored per project/tag/hash combination. Each scan document contains:

| Field | Description |
|-------|-------------|
| `project.repo` | GitHub repository URL |
| `project.name` | Component name (e.g., "OpenSearch Dashboards", "OpenSearch") |
| `project.tag` | Release version or branch (e.g., "2.2.0", "origin/main") |
| `project.hash` | Git commit hash |
| `vulnerabilities[]` | Array of matched CVEs with id, aliases, title, severity, package info |
| `vulnerabilities[].id` | Primary advisory identifier (e.g., "CVE-2020-36604") |
| `vulnerabilities[].aliases` | Alternate IDs (e.g., GHSA, GSD identifiers) |
| `vulnerabilities[].title` | Array of advisory descriptions |
| `vulnerabilities[].severity` | CRITICAL, HIGH, MEDIUM, or LOW |
| `vulnerabilities[].package` | Affected dependency (name, version, purl, ecosystem) |
| `vulnerabilities[].excluded` | If present ("AT_PROJECT" or "AT_RULE"), the CVE is suppressed |
| `count.severe` / `count.minor` | Tallies of non-excluded vulnerabilities |
| `timestamp.scan` | When the scan ran (epoch milliseconds) |
| `timestamp.commit` | Commit timestamp (epoch milliseconds) |

## IAM Permissions

The Lambda needs to assume a role in the OpenSearch account. That role must:

1. Allow the OSCAR Lambda's execution role to assume it (trust policy)
2. Have permissions to query the OpenSearch domain (resource policy)

The cross-account role needs the following permissions on the OpenSearch domain:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost"
      ],
      "Resource": [
        "arn:aws:es:us-east-1:<account-id>:domain/<domain-name>/*"
      ]
    }
  ]
}
```

Required permissions:
- `es:ESHttpGet` — For `/_search` requests
- `es:ESHttpPost` — For aggregation queries (project discovery)

The Lambda's execution role also needs STS AssumeRole permission to assume the cross-account role. Store the role ARN in the `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN` environment variable (set via `.env` / CDK).

## Example DSL Query Requests/Responses

### Query Vulnerabilities (with version and project name)

Request:
```
GET /scans-000164/_search
{
  "size": 100,
  "query": {
    "bool": {
      "filter": [
        {"term": {"project.tag": "2.2.0"}},
        {"term": {"project.name": "OpenSearch Dashboards"}}
      ]
    }
  }
}
```

### Query Vulnerabilities (version only)

Request:
```
GET /scans-000164/_search
{
  "size": 100,
  "query": {
    "bool": {
      "filter": [
        {"term": {"project.tag": "origin/3.7"}}
      ]
    }
  }
}
```

### Query Vulnerabilities (no filters — match all)

Request:
```
GET /scans-000164/_search
{
  "size": 100,
  "query": {
    "match_all": {}
  }
}
```

### List Projects (Aggregation)

Request:
```
POST /scans/_search
{
  "size": 0,
  "aggs": {
    "projects": {
      "terms": { "field": "project.name", "size": 1000 },
      "aggs": {
        "tags": {
          "terms": { "field": "project.tag", "size": 1000 }
        }
      }
    }
  }
}
```

### Response Format (DSL Query)

```json
{
  "took": 42,
  "timed_out": false,
  "_shards": {"total": 5, "successful": 5, "skipped": 0, "failed": 0},
  "hits": {
    "total": {"value": 1, "relation": "eq"},
    "max_score": 0,
    "hits": [
      {
        "_index": "scans-000164",
        "_id": "<document-id>",
        "_score": 0,
        "_source": {
          "project": {
            "repo": "<repo-url>",
            "name": "OpenSearch Dashboards",
            "tag": "2.2.0",
            "hash": "<commit-hash>"
          },
          "vulnerabilities": [
            {
              "id": "CVE-2020-36604",
              "aliases": ["CVE-2020-36604", "GHSA-2r2c-g63r-vccr"],
              "title": ["hoek Prototype Pollution vulnerability"],
              "severity": "CRITICAL",
              "package": {
                "name": "hoek",
                "version": "4.2.1",
                "purl": "pkg:npm/hoek@4.2.1",
                "ecosystem": "npm"
              }
            }
          ],
          "count": {"severe": 11, "minor": 16},
          "timestamp": {"scan": "1719273600000", "commit": "1719187200000"}
        }
      }
    ]
  }
}
```

## Environment Variables

### Secrets Manager (sensitive — stored in security advisories secret)

These values are stored as JSON key-value pairs in an AWS Secrets Manager secret.
The CDK stack creates the secret as `oscar-security-advisories-env-{environment}` (e.g., `oscar-security-advisories-env-dev`).
The `SECURITY_ADVISORIES_SECRET_NAME` environment variable (automatically set by CDK) tells the Lambda which secret to read.

After deployment, populate it:

```bash
aws secretsmanager put-secret-value \
  --secret-id oscar-security-advisories-env-dev \
  --secret-string '{
    "OPENSEARCH_HOST": "https://your-opensearch-endpoint.region.es.amazonaws.com"
  }'
```

| Key | Description | Example |
|-----|-------------|---------|
| `OPENSEARCH_HOST` | Full URL of the OpenSearch endpoint (include `https://`) | `https://your-opensearch-endpoint.region.es.amazonaws.com` |

### CDK Environment Variables (non-sensitive — set via CDK)

These are passed through from `.env` to the Lambda as environment variables. All have sensible defaults.

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSEARCH_REGION` | AWS region of the OpenSearch cluster | `us-east-1` |
| `OPENSEARCH_SERVICE` | AWS service name for SigV4 signing | `es` |
| `OPENSEARCH_REQUEST_TIMEOUT` | Request timeout in seconds | `60` |
| `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN` | IAM role ARN for cross-account OpenSearch access | _(none)_ |

## Monitoring

The agent configures CloudWatch alarms for the following log patterns:

| Pattern | Threshold | Description |
|---------|-----------|-------------|
| `SECURITY_ADVISORIES_DSL_QUERY_FAILED` | 5 occurrences | OpenSearch DSL query failures |
| `SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED` | 2 occurrences | OpenSearch connectivity issues |
| `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED` | 1 occurrence | Cross-account role assumption failure |
