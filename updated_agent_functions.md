# Updated Agent Function Configurations

## Build Metrics Agent - Enhanced Functions

```json
{
  "functions": [
    {
      "name": "get_build_metrics",
      "description": "Get comprehensive build metrics and distribution build analysis",
      "parameters": {
        "query": {
          "type": "string",
          "description": "Natural language query about build status or failures",
          "required": false
        },
        "version": {
          "type": "string",
          "description": "Version number (e.g., 3.2.0)",
          "required": false
        },
        "build_numbers": {
          "type": "array",
          "description": "List of build numbers to analyze",
          "required": false
        },
        "components": {
          "type": "array",
          "description": "List of component names",
          "required": false
        },
        "status_filter": {
          "type": "string",
          "description": "Filter by build status (failed, success)",
          "required": false
        },
        "time_range": {
          "type": "string",
          "description": "Time range for analysis (7d, 30d)",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    },
    {
      "name": "resolve_components_from_builds",
      "description": "Resolve which components are associated with specific build numbers",
      "parameters": {
        "version": {
          "type": "string",
          "description": "Version number",
          "required": true
        },
        "build_numbers": {
          "type": "array",
          "description": "List of build numbers to resolve",
          "required": true
        }
      },
      "requireConfirmation": "DISABLED"
    }
  ]
}
```

## Release Metrics Agent - Enhanced Functions

```json
{
  "functions": [
    {
      "name": "get_release_metrics",
      "description": "Get comprehensive release readiness metrics and component analysis",
      "parameters": {
        "query": {
          "type": "string",
          "description": "Natural language query about release readiness or status",
          "required": false
        },
        "version": {
          "type": "string", 
          "description": "Version number (e.g., 3.2.0)",
          "required": false
        },
        "components": {
          "type": "array",
          "description": "List of component names",
          "required": false
        },
        "time_range": {
          "type": "string",
          "description": "Time range for analysis (7d, 30d)",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    },
    {
      "name": "resolve_components_from_builds",
      "description": "Resolve which components are associated with specific build numbers",
      "parameters": {
        "version": {
          "type": "string",
          "description": "Version number",
          "required": true
        },
        "build_numbers": {
          "type": "array",
          "description": "List of build numbers to resolve",
          "required": true
        }
      },
      "requireConfirmation": "DISABLED"
    }
  ]
}
```

## Key Changes Made:

1. **Added `resolve_components_from_builds` to Build and Release agents** - This enables cross-referencing between build numbers and components across all agents

2. **Fixed function routing in lambda** - Added specific handlers for `resolve_components_from_builds` and `get_rc_build_mapping`

3. **Added data source tracking** - Each response now includes information about which OpenSearch index was queried

4. **Consistent parameter handling** - All agents now handle the same core functions for cross-agent compatibility

## Deployment Steps:

1. **Update Bedrock Agent Configurations**:
   - Add the `resolve_components_from_builds` function to Build and Release agents
   - Ensure all function schemas match the updated configurations

2. **Deploy Updated Lambda Function**:
   ```bash
   ./update_metrics_code_only.sh
   ```

3. **Test Cross-Agent Functionality**:
   - Test RC resolution across all agents
   - Verify component mapping works consistently
   - Check data source information appears in responses