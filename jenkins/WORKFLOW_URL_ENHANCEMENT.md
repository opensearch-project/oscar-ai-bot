# Jenkins Workflow URL Enhancement

## Overview

This enhancement adds workflow URL support to the Jenkins integration, allowing the final response to include a direct link to the specific workflow execution (e.g., `https://build.ci.opensearch.org/job/docker-scan/5249/`).

## Problem

Previously, when triggering Jenkins jobs, the response only included:
- Job URL (general job page)
- Queue location (temporary queue item)

Users requested that the workflow URL (specific build execution) be included in the final response to make it easier to monitor the specific job execution.

## Solution

### Changes Made

1. **Enhanced JenkinsClient.trigger_job()** (`jenkins_client.py`)
   - Added `_get_build_number_from_queue()` helper method
   - Polls the Jenkins queue API to get the build number once job starts executing
   - Includes `build_number` and `workflow_url` in the response when available

2. **Enhanced Lambda Response** (`lambda_function.py`)
   - Modified `handle_trigger_job()` to include workflow URL in success message
   - Updated response format to be more user-friendly

3. **Added Config Method** (`config.py`)
   - Added `get_workflow_url()` method for consistent URL generation

### Technical Details

#### Queue Polling Logic
```python
def _get_build_number_from_queue(self, queue_location: str, auth: HTTPBasicAuth, max_attempts: int = 10) -> Optional[int]:
```

- Polls the Jenkins queue API up to 10 times (with 1-second intervals)
- Looks for the `executable.number` field in the queue response
- Returns the build number once the job starts executing
- Handles timeouts and errors gracefully

#### Enhanced Response Format

**Before:**
```json
{
  "status": "success",
  "message": "Successfully triggered Jenkins job: docker-scan",
  "job_url": "https://build.ci.opensearch.org/job/docker-scan",
  "queue_location": "https://build.ci.opensearch.org/queue/item/107720/"
}
```

**After:**
```json
{
  "status": "success",
  "message": "Success! I've triggered the docker-scan job.\nYou can monitor the job progress at: https://build.ci.opensearch.org/job/docker-scan\nThe job has been queued with location: https://build.ci.opensearch.org/queue/item/107720/\nWorkflow URL: https://build.ci.opensearch.org/job/docker-scan/5249/",
  "job_url": "https://build.ci.opensearch.org/job/docker-scan",
  "queue_location": "https://build.ci.opensearch.org/queue/item/107720/",
  "build_number": 5249,
  "workflow_url": "https://build.ci.opensearch.org/job/docker-scan/5249/"
}
```

## Usage Example

When a user triggers a job:

```
User: run docker scan on alpine:3.19
Agent: I found the details for the docker-scan job...
User: yes
Agent: Success! I've triggered the docker-scan job.
       You can monitor the job progress at: https://build.ci.opensearch.org/job/docker-scan
       The job has been queued with location: https://build.ci.opensearch.org/queue/item/107720/
       Workflow URL: https://build.ci.opensearch.org/job/docker-scan/5249/
```

## Fallback Behavior

- If queue polling fails or times out, the response still includes the job URL and queue location
- The workflow URL is only included when successfully obtained
- No breaking changes to existing functionality

## Performance Impact

- Adds 1-10 seconds to job trigger response time (due to queue polling)
- Uses minimal additional API calls (1-10 GET requests to queue API)
- Polling is limited and has timeouts to prevent hanging

## Testing

Run the test script to verify functionality:
```bash
python3 jenkins/test_workflow_url.py
```

## Files Modified

- `jenkins/jenkins_client.py` - Added queue polling and workflow URL logic
- `jenkins/lambda_function.py` - Enhanced response message formatting
- `jenkins/config.py` - Added workflow URL generation method
- `jenkins/test_workflow_url.py` - Test script (new)
- `jenkins/WORKFLOW_URL_ENHANCEMENT.md` - This documentation (new)