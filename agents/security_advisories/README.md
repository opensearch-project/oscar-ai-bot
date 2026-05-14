# Security Advisories Agent

The Security Advisories agent gives OSCAR the ability to query CVEs and security vulnerabilities affecting OpenSearch project components through Slack. It connects to a cross-account OpenSearch cluster via STS AssumeRole and AWS SigV4 authentication, using OpenSearch Agentic Search to translate natural language queries into DSL.

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
    ├─ Query Enhancer (appends version + project context to NL query)
    ├─ Agentic Search Client (GET /_search?search_pipeline=...)
    │       │
    │       ▼
    │   OpenSearch Cluster
    │       ├─ Flow Agent (translates NL → DSL via QueryPlanningTool)
    │       └─ Returns hits + generated DSL
    │       │
    ├─ Response Filter (severity, exclusion, age filtering)
    └─ Summary Builder (severity count aggregation)
```

## How It Works

1. **Cross-Account Access** — The Lambda assumes a role in the OpenSearch account using STS, then signs requests with SigV4.
2. **Query Enhancement** — The version and project name (if provided) are appended to the natural language query for context.
3. **Agentic Search** — The enhanced query is sent to OpenSearch with a search pipeline parameter. The flow agent on the cluster translates the natural language to DSL and executes the query.
4. **Post-Query Filtering** — Results are filtered by severity level, exclusion status, and scan age at the application layer (these array-level filters can't be efficiently done in OpenSearch DSL).

**Project Discovery** — The `list_projects` function uses terms aggregations to enumerate available projects and their tags without agentic search. This is especially useful when queries reference relative terms like "latest release" or "most recent version" — the agent calls `list_projects` first to resolve the concrete version before querying vulnerabilities.

## Bedrock Functions

| Function | Description |
|----------|-------------|
| `query_vulnerabilities` | Query CVEs using natural language via the agentic pipeline |
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

## Agentic Pipeline Prerequisites

Before the Security Advisories agent can use agentic search, the OpenSearch cluster must have the following configured:

### 1. ML Model Registration

Register an LLM model in the OpenSearch ML framework that the flow agent will use for query translation:

```bash
POST /_plugins/_ml/models/_register
{
  "name": "query-planning-model",
  "function_name": "remote",
  "connector_id": "<your-connector-id>"
}
```

### 2. Flow Agent Creation

Create a flow agent with QueryPlanningTool configured for the scans index:

```bash
POST /_plugins/_ml/agents/_register
{
  "name": "oscar-agent",
  "type": "flow",
  "tools": [
    {
      "type": "QueryPlanningTool",
      "parameters": {
        "model_id": "<registered-model-id>"
      }
    }
  ]
}
```

### 3. Agentic Search Pipeline Creation

Create a search pipeline with `agentic_query_translator` request processor and `agentic_context` response processor:

```bash
PUT /_search/pipeline/oscar-agentic-pipeline
{
  "request_processors": [
    {
      "agentic_query_translator": {
        "agent_id": "<oscar-agent-id>"
      }
    }
  ],
  "response_processors": [
    {
      "agentic_context": {
        "agent_steps_summary": true,
        "dsl_query": true
      }
    }
  ]
}
```

This pipeline is used for the scans index.

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
- `es:ESHttpGet` — For `/_search` requests with `search_pipeline` parameter
- `es:ESHttpPost` — For aggregation queries (project discovery)

The Lambda's execution role also needs STS AssumeRole permission to assume the cross-account role. Store the role ARN in the `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN` environment variable (set via `.env` / CDK).

## Example Agentic Search Requests/Responses

### Query Vulnerabilities

Request:
```
GET /scans/_search?search_pipeline=oscar-agentic-pipeline
{
  "query": {
    "agentic": {
      "query_text": "Show me critical CVEs for Dashboards version 2.2.0"
    }
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

### Response Format (Agentic Search)

```json
{
  "took": 1419,
  "timed_out": false,
  "_shards": {"total": 5, "successful": 5, "skipped": 0, "failed": 0},
  "hits": {
    "total": {"value": 1, "relation": "eq"},
    "max_score": 0,
    "hits": [
      {
        "_index": "scans",
        "_id": "<document-id>",
        "_score": 0,
        "_source": {
          "project": {
            "repo": "<repo-url>",
            "name": "<project-name>",
            "tag": "<release-version>",
            "hash": "<commit-hash>"
          },
          "vulnerabilities": [
            {
              "id": "<cve-id>",
              "aliases": ["<cve-id>", "<ghsa-id>"],
              "title": ["<advisory description>"],
              "severity": "CRITICAL",
              "package": {
                "name": "<package-name>",
                "version": "<package-version>",
                "purl": "pkg:npm/<package-name>@<package-version>",
                "ecosystem": "npm"
              }
            }
          ],
          "count": {"severe": 11, "minor": 16},
          "timestamp": {"scan": "<epoch-ms>", "commit": "<epoch-ms>"}
        }
      }
    ]
  },
  "ext": {
    "dsl_query": {
      "size": 10,
      "query": {
        "bool": {
          "filter": [
            {"term": {"project.name": "<project-name>"}},
            {"term": {"project.tag": "<release-version"}},
            {"nested": {"path": "vulnerabilities", "query": {"match_all": {}}}}
          ]
        }
      }
    }
  }
}
```

The `ext.dsl_query` field contains the DSL query generated by the flow agent, useful for debugging query translation issues.

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
| `SCANS_INDEX` | Index name for scan documents | `scans` |
| `AGENTIC_PIPELINE` | Agentic search pipeline name | `oscar-agentic-pipeline` |
| `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN` | IAM role ARN for cross-account OpenSearch access | _(none)_ |

## Monitoring

The agent configures CloudWatch alarms for the following log patterns:

| Pattern | Threshold | Description |
|---------|-----------|-------------|
| `SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED` | 5 occurrences | OpenSearch agentic query failures |
| `SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED` | 2 occurrences | OpenSearch connectivity issues |
| `SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED` | 1 occurrence | Cross-account role assumption failure |

## Notes

- If the agentic pipeline fails, the Lambda returns an error to the Bedrock agent rather than falling back to a raw DSL query.
- The flow agent is stateless (single-pass) — conversational continuity is handled by the Bedrock session, not OpenSearch.
