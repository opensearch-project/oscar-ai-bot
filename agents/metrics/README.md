# Metrics Agent

The Metrics agent gives OSCAR the ability to query OpenSearch metrics data — integration test results, build results, and release readiness — through Slack. It connects to a cross-account OpenSearch cluster via STS AssumeRole and AWS SigV4 authentication, using OpenSearch Agentic Search to translate natural language queries into DSL.

## Architecture

```
User in Slack
    │
    ▼
Supervisor Agent
    │
    ▼
Unified Metrics-Specialist Agent
    │
    ▼
Metrics Lambda
    ├─ Index Router (keyword matching → build/test/release)
    ├─ Query Enhancer (appends version + filters to NL query)
    ├─ Agentic Search Client (POST /_search?search_pipeline=...)
    │       │
    │       ▼
    │   OpenSearch Cluster
    │       ├─ Flow Agent (translates NL → DSL via QueryPlanningTool)
    │       └─ Returns hits + generated DSL
    │       │
    ├─ Response Extractor (hits.hits[]._source)
    ├─ Data Processors (deduplication)
    └─ Summary Generators (human-readable summaries)
```

## How It Works

1. **Cross-Account Access** — The Lambda assumes a role in the OpenSearch account using STS, then signs requests with SigV4.
2. **Index Routing** — Incoming queries are classified by keyword matching ('build', 'test', 'integration', 'release', 'readiness') to determine the target index and agentic pipeline.
3. **Query Enhancement** — The version and any explicit filters (components, status, platform, architecture) are appended to the natural language query.
4. **Agentic Search** — The enhanced query is sent to OpenSearch with a search pipeline parameter. The flow agent on the cluster translates the natural language to DSL and executes the query.
5. **Data Processing** — Results are deduplicated, aggregated, and summarized before being returned to the Bedrock agent.

## Agentic Pipeline Prerequisites

Before the Metrics agent can use agentic search, the OpenSearch cluster must have the following configured:

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

Create a flow agent with QueryPlanningTool configured for each index type:

```bash
POST /_plugins/_ml/agents/_register
{
  "name": "metrics-agent",
  "type": "flow",
  "tools": [
    {
      "type": "QueryPlanningTool",
      "parameters": {
        "model_id": "<registered-model-id>",
        "index": "opensearch-distribution-build-results-03-2026"
      }
    }
  ]
}
```

Repeat for test and release indices with appropriate index names (year-based for build/test, static for release).

### 3. Agentic Search Pipeline Creation

Create a single search pipeline shared across all indices with `agentic_query_translator` request processor and `agentic_context` response processor:

```bash
PUT /_search/pipeline/metrics-agentic-pipeline
{
  "request_processors": [
    {
      "agentic_query_translator": {
        "agent_id": "<metrics-agent-id>"
      }
    }
  ],
  "response_processors": [
    {
      "agentic_context": {}
    }
  ]
}
```

This single pipeline is used for all metrics indices:
- `opensearch-distribution-build-results-{month}-{year}`
- `opensearch-integration-test-results-{month}-{year}`
- `opensearch_release_metrics`

### 4. Release Readiness Pipeline

Release readiness uses a **second, differently shaped pipeline**. The metrics pipeline is
backed by a *conversational* agent that routes indices itself (`ListIndexTool` +
`IndexMappingTool`) and keeps conversation memory. The release pipeline is backed by a
*flow* agent holding a single `QueryPlanningTool`:

```bash
PUT /_search/pipeline/release-flow-agentic-pipeline
{
  "request_processors": [
    { "agentic_query_translator": { "agent_id": "<release-flow-agent-id>" } }
  ],
  "response_processors": [
    { "agentic_context": { "dsl_query": true } }
  ]
}
```

Two consequences for the Lambda, both handled in `agentic_search()`:

- The **index must be in the request path** (`/opensearch_release_state/_search?...`). It
  is the only way a flow agent's planner receives a mapping, and it keeps index selection
  deterministic rather than LLM-decided.
- **No `memory_id`**: a flow agent has no memory, unlike the conversational metrics agent.

The flow agent carries a release-specific `query_planner_system_prompt` describing both
release indices. Its most important rules: filter on `.keyword` sub-fields (both indices
are dynamically mapped, so `product` is analyzed text and a bare `term` misses
`opensearch-dashboards`), always sort by `last_checked` descending because
`opensearch_release_state` is append-only history, and never answer timing questions from
the state index because its `release_date`/`days_to_release` are stale snapshots.

The planner's output is never trusted for completeness: `get_release_status` and
`get_release_window` build fixed DSL instead, since the rubric's verdict is only correct if
it sees every criterion. Only `query_release_state` goes through this pipeline.

Release indices:
- `opensearch_release_state` — per-criterion readiness history
- `opensearch_release_schedule` — one record per release version

## IAM Permissions

The cross-account role assumed by the Lambda needs the following permissions on the OpenSearch domain:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet"
      ],
      "Resource": [
        "arn:aws:es:us-east-1:123456789012:domain/your-domain/*"
      ]
    }
  ]
}
```

Required permissions:
- `es:ESHttpGet` — For `/_search` requests with `search_pipeline` parameter and ML model access

The Lambda's execution role also needs STS AssumeRole permission to assume the cross-account role.

## Example Agentic Search Requests/Responses

### Build Metrics

Request:
```
GET /opensearch-distribution-build-results-03-2026/_search?search_pipeline=metrics-agentic-pipeline
{
  "query": {
    "agentic": {
      "query_text": "Show build results for version 3.0.0"
    }
  }
}
```

### Test Metrics

Request:
```
GET /opensearch-integration-test-results-03-2026/_search?search_pipeline=metrics-agentic-pipeline
{
  "query": {
    "agentic": {
      "query_text": "Show failed integration tests for version 3.2.0 RC1 on linux x64"
    }
  }
}
```

### Release Metrics

Request:
```
GET /opensearch_release_metrics/_search?search_pipeline=metrics-agentic-pipeline
{
  "query": {
    "agentic": {
      "query_text": "Show release readiness for version 3.2.0"
    }
  }
}
```

### Response Format

```json
{
  "hits": {
    "total": {"value": 42},
    "hits": [
      {"_source": { "...document fields..." }}
    ]
  },
  "ext": {
    "dsl_query": {
      "bool": {
        "must": [
          {"match": {"version": "3.2.0"}}
        ]
      }
    }
  }
}
```

The `ext.dsl_query` field contains the DSL query generated by the flow agent, useful for debugging query translation issues.

## Environment Variables

### Secrets Manager (sensitive — stored in metrics secret)

These values are stored as JSON key-value pairs in an AWS Secrets Manager secret.
The CDK stack creates the secret as `oscar-metrics-env-{environment}` (e.g., `oscar-metrics-env-dev`).

After deployment, populate it:

```bash
aws secretsmanager put-secret-value \
  --secret-id oscar-metrics-env-dev \
  --secret-string '{
    "METRICS_CROSS_ACCOUNT_ROLE_ARN": "arn:aws:iam::your-opensearch-account:role/OpenSearchOscarAccessRole",
    "OPENSEARCH_HOST": "https://your-opensearch-endpoint.region.es.amazonaws.com"
  }'
```

| Key | Description | Example |
|-----|-------------|---------|
| `METRICS_CROSS_ACCOUNT_ROLE_ARN` | IAM role ARN in the OpenSearch account that the Lambda assumes for cross-account access | `arn:aws:iam::123456789012:role/OpenSearchOscarAccessRole` |
| `OPENSEARCH_HOST` | Full URL of the OpenSearch endpoint (include `https://`) | `https://search-metrics.us-east-1.es.amazonaws.com` |

### Secret Format

The metrics secret is stored in **JSON format**. The Lambda reads it via `json.loads()` and extracts individual keys:

```json
{
  "METRICS_CROSS_ACCOUNT_ROLE_ARN": "arn:aws:iam::123456789012:role/OpenSearchOscarAccessRole",
  "OPENSEARCH_HOST": "https://your-opensearch-endpoint.region.es.amazonaws.com"
}
```

The `METRICS_SECRET_NAME` environment variable (automatically set by CDK) tells the Lambda which secret to read.

### CDK Environment Variables (non-sensitive — set via CDK)

These are passed through from `.env` to the Lambda as environment variables. All have sensible defaults.

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENSEARCH_REGION` | AWS region of the OpenSearch cluster | `us-east-1` |
| `OPENSEARCH_SERVICE` | AWS service name for SigV4 signing | `es` |
| `OPENSEARCH_LARGE_QUERY_SIZE` | Max documents per query | `1000` |
| `OPENSEARCH_REQUEST_TIMEOUT` | Request timeout in seconds | `60` |
| `AGENTIC_PIPELINE` | Agentic search pipeline name for the build, test and release-metrics indices (conversational agent) | `metrics-agentic-pipeline` |
| `AGENTIC_SEARCH_TIMEOUT` | Timeout in seconds for agentic search requests | `120` |
| `RELEASE_AGENTIC_PIPELINE` | Agentic search pipeline name for the release indices (flow agent) | `release-flow-agentic-pipeline` |
| `RELEASE_STATE_INDEX` | Per-criterion release readiness index | `opensearch_release_state` |
| `RELEASE_SCHEDULE_INDEX` | Release schedule index | `opensearch_release_schedule` |

> **Note:** Build and test index names (`OPENSEARCH_INTEGRATION_TEST_INDEX`, etc.) are no longer configured as env vars.
> The conversational agent on OpenSearch handles that index routing automatically via `ListIndexTool` and `IndexMappingTool`.
> The release indices are named explicitly because the deterministic release handlers build their own DSL and the release flow agent needs the index in the request path.

## Cross-Account Role Setup

The Lambda needs to assume a role in the OpenSearch account. That role must:

1. Allow the OSCAR Lambda's execution role to assume it (trust policy)
2. Have permissions to query the OpenSearch domain (resource policy)
3. Have permissions for agentic search operations (see IAM Permissions section above)

Store the role ARN in the metrics secret as `METRICS_CROSS_ACCOUNT_ROLE_ARN`.

## Notes

- Agentic search is the sole query mechanism — there is no fallback to manual DSL queries.
- The unified Metrics-Specialist agent replaces the previous three specialist agents (build, test, release).
- Helper functions `resolve_components_from_builds` and `get_rc_build_mapping` still use direct DSL queries for specific lookups.
