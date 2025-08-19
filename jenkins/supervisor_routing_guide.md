# OSCAR Supervisor Agent - Jenkins Routing Guide

## Jenkins Request Detection
Route requests to the Jenkins specialist when users mention:
- "scan" + image name (e.g., "scan alpine:3.19")
- "docker scan" or "security scan"
- "run jenkins job" or "trigger job"
- "promote version" or "release promotion"
- Jenkins job names (docker-scan, Pipeline central-release-promotion)
- "what jenkins jobs are available"

## Mandatory Jenkins Workflow

### Step 1: Job Discovery
Call Jenkins specialist `get_job_info` function to understand job requirements.

### Step 2: Parameter Extraction
Extract parameters from user request and map to job requirements.

### Step 3: User Confirmation
Present job details to user in this format:

```
🔧 **Jenkins Job Ready for Execution**

**Job Details:**
- **Job Name:** docker-scan
- **Description:** Docker security vulnerability scan
- **Jenkins URL:** https://build.ci.opensearch.org/job/docker-scan
- **Parameters:**
  - IMAGE_FULL_NAME: alpine:3.19
- **Estimated Duration:** 5-10 minutes

**⚠️ Confirmation Required**
Please confirm to proceed:
- Reply 'yes' or 'confirm' to execute
- Reply 'cancel' to abort
```

### Step 4: Job Execution (Only After Confirmation)
If user confirms, call Jenkins specialist `trigger_job` function.

## Critical Rules
- NEVER call `trigger_job` without user confirmation
- ALWAYS call `get_job_info` first to understand job requirements
- Present complete job details before requesting confirmation
- Handle Jenkins authentication errors gracefully

## Example Flow
User: "Run docker scan on alpine:3.19"
1. Call Jenkins `get_job_info("docker-scan")`
2. Extract IMAGE_FULL_NAME = "alpine:3.19"
3. Present confirmation dialog
4. Wait for user confirmation
5. Call Jenkins `trigger_job` with parameters