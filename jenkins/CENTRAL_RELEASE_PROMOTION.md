# Central Release Promotion Job Implementation

## Overview

Successfully implemented support for the "Pipeline central-release-promotion" Jenkins job. This job promotes OpenSearch and OpenSearch Dashboards release candidates to final release.

## Implementation Details

### Job Definition
- **Job Name**: `Pipeline central-release-promotion` (matches actual Jenkins job name)
- **Description**: Promotes OpenSearch and OpenSearch Dashboards release candidates to final release
- **Parameters**:
  - `RELEASE_VERSION` (required): Release version in semantic format (e.g., 2.11.0, 3.0.0)
  - `OPENSEARCH_RC_BUILD_NUMBER` (required): OpenSearch Release Candidate Build Number
  - `OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER` (required): OpenSearch Dashboards Release Candidate Build Number

### Parameter Validation
- Version format validation using regex pattern `^\d+\.\d+\.\d+$`
- All parameters are required (no defaults)
- Proper error messages for missing or invalid parameters

### Agent Integration Flow

The agent can discover and use this job through the generic action group functions:

1. **Discovery**: Agent calls `list_jobs` to see all available jobs
2. **Parameter Discovery**: Agent calls `get_job_info` with `job_name="Pipeline central-release-promotion"`
3. **Job Execution**: Agent calls `trigger_job` with:
   - `job_name="Pipeline central-release-promotion"`
   - `RELEASE_VERSION="2.11.0"`
   - `OPENSEARCH_RC_BUILD_NUMBER="123"`
   - `OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER="456"`

### Example Agent Interactions

#### 1. Get Job Information
```json
{
  "function": "get_job_info",
  "parameters": [
    {"name": "job_name", "value": "Pipeline central-release-promotion"}
  ]
}
```

**Response**:
```json
{
  "status": "success",
  "job_name": "Pipeline central-release-promotion",
  "description": "Promotes OpenSearch and OpenSearch Dashboards release candidates to final release...",
  "parameter_definitions": {
    "RELEASE_VERSION": {
      "description": "Release version (e.g., 2.11.0, 3.0.0)",
      "required": true,
      "type": "string",
      "validation_pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "OPENSEARCH_RC_BUILD_NUMBER": {
      "description": "OpenSearch Release Candidate Build Number",
      "required": true,
      "type": "string"
    },
    "OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER": {
      "description": "OpenSearch Dashboards Release Candidate Build Number",
      "required": true,
      "type": "string"
    }
  }
}
```

#### 2. Trigger Job
```json
{
  "function": "trigger_job",
  "parameters": [
    {"name": "job_name", "value": "Pipeline central-release-promotion"},
    {"name": "RELEASE_VERSION", "value": "2.11.0"},
    {"name": "OPENSEARCH_RC_BUILD_NUMBER", "value": "123"},
    {"name": "OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER", "value": "456"}
  ]
}
```

### Slack Usage Examples

Users can interact with this job through natural language in Slack:

- "Promote version 2.11.0 with OpenSearch RC 123 and Dashboards RC 456"
- "Run central release promotion for version 3.0.0"
- "Start the release promotion pipeline for 2.11.0"

The agent will:
1. Understand the intent to run a release promotion
2. Extract the version and build numbers from the message
3. Call `get_job_info` to understand the job requirements
4. Call `trigger_job` with the correct parameters

## Code Changes Made

### 1. Job Definition (`jenkins/job_definitions.py`)
- Added `CentralReleasePromotionJob` class
- Implemented parameter validation with regex pattern
- Registered job in the default job registry

### 2. Lambda Function (`jenkins/lambda_function.py`)
- Enhanced `handle_trigger_job` to accept individual parameters
- Maintained backward compatibility with JSON parameter format
- Improved parameter extraction logic

### 3. Configuration (`jenkins/config.py`)
- Improved local testing support (no Jenkins credentials required for job registration tests)
- Better validation logic for Lambda vs local environments

### 4. Action Group Schema (`jenkins/schemas/jenkins_action_group.json`)
- Updated `trigger_job` description to clarify parameter handling
- Emphasized the workflow: get_job_info → trigger_job

## Testing

### Local Testing
```bash
python jenkins/test_job_registration.py
```

This test verifies:
- Job is properly registered
- Parameter definitions are correct
- Parameter validation works
- No Jenkins credentials required

### Integration Testing
Once deployed, test with:
```bash
python jenkins/test_config.py  # Requires AWS credentials
```

## Deployment

Use the update script to deploy code changes:
```bash
./jenkins/deployment/update_lambda.sh
```

This preserves existing permissions and only updates the Lambda code.

## Security & Validation

- All parameters are validated before sending to Jenkins
- Version format is strictly validated with regex
- Required parameters are enforced
- Proper error messages guide users on correct usage
- No sensitive information is logged (credentials are masked)

## Future Enhancements

1. **Build Number Validation**: Could add validation for build number formats
2. **Version Existence Check**: Could verify the RC builds exist before promotion
3. **Status Monitoring**: Could add job status checking capabilities
4. **Rollback Support**: Could add rollback functionality if promotion fails

## Notes

- Job name matches exactly with Jenkins: "Pipeline central-release-promotion"
- Uses generic `trigger_job` action group function (no job-specific action needed)
- Agent discovers job capabilities dynamically through `get_job_info`
- Supports both individual parameters and legacy JSON parameter format
- Fully integrated with existing Jenkins client infrastructure