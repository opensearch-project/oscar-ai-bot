# Updated Action Group Function Schemas - Simplified Approach

## 🎯 Overview

These updated function schemas align with our simplified metrics system and ensure the supervisor agent can pass all necessary parameters to the collaborator agents.

---

## 🧪 Integration Test Metrics Agent

### Action Group: `integration-test-metrics-actions`
### Lambda Function: `oscar-test-metrics-agent-new`

```json
{
  "functions": [
    {
      "name": "get_integration_test_metrics",
      "description": "Retrieve comprehensive integration test results including pass/fail rates, component testing, and security test outcomes",
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze (e.g., '3.2.0', '2.18.0') - REQUIRED",
          "required": true
        },
        "rc_numbers": {
          "type": "string",
          "description": "Comma-separated RC numbers to analyze (e.g., '1,2,3' or '1')",
          "required": false
        },
        "build_numbers": {
          "type": "string", 
          "description": "Comma-separated distribution build numbers to analyze (e.g., '12345,12346')",
          "required": false
        },
        "integ_test_build_numbers": {
          "type": "string",
          "description": "Comma-separated integration test build numbers to analyze",
          "required": false
        },
        "components": {
          "type": "string",
          "description": "Comma-separated component names to focus on (e.g., 'OpenSearch,OpenSearch-Dashboards')",
          "required": false
        },
        "status_filter": {
          "type": "string",
          "description": "Filter by test status: 'passed' or 'failed'",
          "required": false
        },
        "distribution": {
          "type": "string",
          "description": "Distribution type: 'tar', 'rpm', or 'deb' (default: 'tar')",
          "required": false
        },
        "architecture": {
          "type": "string", 
          "description": "Architecture: 'x64' or 'arm64' (default: 'x64')",
          "required": false
        },
        "platform": {
          "type": "string",
          "description": "Platform: 'linux' or 'windows' (default: 'linux')",
          "required": false
        },
        "with_security": {
          "type": "string",
          "description": "Filter security tests: 'pass' or 'fail'",
          "required": false
        },
        "without_security": {
          "type": "string",
          "description": "Filter non-security tests: 'pass' or 'fail'",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    },
    {
      "name": "get_test_metrics",
      "description": "Generic test metrics retrieval function",
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze - REQUIRED",
          "required": true
        },
        "query": {
          "type": "string",
          "description": "Natural language query for test metrics",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    }
  ]
}
```

---

## 🏗️ Build Metrics Agent

### Action Group: `build-metrics-actions`
### Lambda Function: `oscar-build-metrics-agent-new`

```json
{
  "functions": [
    {
      "name": "get_build_metrics",
      "description": "Retrieve comprehensive build performance metrics including success rates, failure patterns, and component build results",
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze (e.g., '3.2.0', '2.18.0') - REQUIRED",
          "required": true
        },
        "build_numbers": {
          "type": "string",
          "description": "Comma-separated distribution build numbers to analyze (e.g., '12345,12346')",
          "required": false
        },
        "components": {
          "type": "string",
          "description": "Comma-separated component names to focus on (e.g., 'OpenSearch,OpenSearch-Dashboards')",
          "required": false
        },
        "status_filter": {
          "type": "string",
          "description": "Filter by build status: 'passed' or 'failed'",
          "required": false
        },
        "rc_numbers": {
          "type": "string",
          "description": "Comma-separated RC numbers to analyze (e.g., '1,2,3')",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    },
    {
      "name": "get_metrics",
      "description": "Generic build metrics retrieval function",
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze - REQUIRED",
          "required": true
        },
        "query": {
          "type": "string",
          "description": "Natural language query for build metrics",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    }
  ]
}
```

---

## 🚀 Release Metrics Agent

### Action Group: `release-metrics-actions`
### Lambda Function: `oscar-release-metrics-agent-new`

```json
{
  "functions": [
    {
      "name": "get_release_metrics",
      "description": "Retrieve comprehensive release readiness metrics including release state, issue management, and component preparedness",
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze (e.g., '3.2.0', '2.18.0') - REQUIRED",
          "required": true
        },
        "components": {
          "type": "string",
          "description": "Comma-separated component names to focus on (e.g., 'OpenSearch,OpenSearch-Dashboards')",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    },
    {
      "name": "get_metrics",
      "description": "Generic release metrics retrieval function", 
      "parameters": {
        "version": {
          "type": "string",
          "description": "OpenSearch version to analyze - REQUIRED",
          "required": true
        },
        "query": {
          "type": "string",
          "description": "Natural language query for release metrics",
          "required": false
        }
      },
      "requireConfirmation": "DISABLED"
    }
  ]
}
```

---

## 🔧 Key Schema Design Decisions

### **1. Version Parameter**
- **Required**: `true` for all primary functions
- **Rationale**: Our simplified system requires version for all queries

### **2. String-Based Arrays**
- **Format**: Comma-separated strings (e.g., `"1,2,3"`)
- **Rationale**: Bedrock handles strings better than arrays, our code parses them

### **3. Flexible Parameters**
- **Integration Test Agent**: Most parameters (11 total) for maximum flexibility
- **Build Agent**: Focused parameters (5 total) for build-specific queries
- **Release Agent**: Minimal parameters (2 total) for release readiness

### **4. Generic Functions**
- **Purpose**: Fallback functions for natural language queries
- **Parameters**: Version + optional query text

---

## 🧪 Testing the Updated Schemas

### Test Cases to Validate:

#### **Integration Test Agent**
```bash
# Version only
"Show me integration test results for version 3.2.0"

# With status filter
"Show me failed integration tests for version 3.2.0"

# With components
"Show me OpenSearch-Dashboards integration test results for version 3.2.0"

# With RC numbers
"Show me integration test results for version 3.2.0 RC 1 and RC 2"

# With security filters
"Show me failed security tests for version 3.2.0"
```

#### **Build Agent**
```bash
# Version only
"Show me build results for version 3.2.0"

# With status filter
"Show me failed builds for version 3.2.0"

# With components
"Show me OpenSearch build performance for version 3.2.0"

# With build numbers
"Show me results for build numbers 12345,12346 for version 3.2.0"
```

#### **Release Agent**
```bash
# Version only
"Show me release readiness for version 3.2.0"

# With components
"Show me OpenSearch-Dashboards release readiness for version 3.2.0"

# Release blockers
"What are the release blockers for version 3.2.0"
```

---

## 🚀 Implementation Steps

### **1. Update Action Groups in AWS Console**
For each agent:
1. Go to Amazon Bedrock → Agents → [Agent Name] → Action Groups
2. Edit the existing action group
3. Replace the function schema with the updated JSON above
4. Save and create new agent version
5. Update agent alias to point to new version

### **2. Verify Parameter Passing**
- Test that supervisor agent can pass all defined parameters
- Confirm Lambda functions receive parameters correctly
- Validate parameter parsing and normalization

### **3. Test End-to-End Flow**
- Supervisor agent query → Action group schema → Lambda function → Response
- Verify all parameter combinations work as expected

---

## ✅ Expected Benefits

After updating the schemas:

1. **Complete Parameter Coverage**: All parameters our simplified system expects
2. **Flexible Querying**: Supervisor can pass any combination of parameters
3. **Better Routing**: More specific function descriptions help supervisor routing
4. **Consistent Interface**: Standardized parameter names across all agents
5. **Natural Language Support**: Generic functions for complex queries

The updated schemas ensure the supervisor agent has full access to all the parameter flexibility our simplified metrics system provides! 🎯