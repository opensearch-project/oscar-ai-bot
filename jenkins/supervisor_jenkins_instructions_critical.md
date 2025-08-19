# CRITICAL: Jenkins Workflow Instructions for Supervisor Agent

## MANDATORY TWO-PHASE JENKINS WORKFLOW

**NEVER call `trigger_job` directly. ALWAYS follow this exact sequence:**

### Phase 1: Information Gathering (REQUIRED FIRST STEP)
When user requests Jenkins job execution:
1. **ALWAYS call `get_job_info` first** - this does NOT execute anything
2. **ALWAYS present confirmation to user** with job details
3. **WAIT for user confirmation** before proceeding

### Phase 2: Execution (ONLY AFTER CONFIRMATION)
After user confirms:
1. **ONLY THEN call `trigger_job`** with proper parameters
2. Present execution results

## ROUTING RULES

### For ANY Jenkins request (docker scan, job trigger, etc.):
```
User Request: "Run docker scan on alpine:3.19"
↓
STEP 1: Route to Jenkins specialist with get_job_info
↓
STEP 2: Present confirmation: "Ready to run docker-scan job on alpine:3.19. Proceed?"
↓
STEP 3: Wait for user confirmation
↓
STEP 4: Route to Jenkins specialist with trigger_job
```

### NEVER DO THIS:
```
User Request: "Run docker scan on alpine:3.19"
↓
❌ WRONG: Route directly to trigger_job
```

## FUNCTION MAPPING

- **Information gathering**: Use `get_job_info` function
- **Job execution**: Use `trigger_job` function (ONLY after confirmation)

## PARAMETER EXTRACTION

For docker scan requests like "Run docker scan on alpine:3.19":
- Extract image name: `alpine:3.19`
- For `get_job_info`: Pass `job_name=docker-scan`
- For `trigger_job`: Pass `job_name=docker-scan` AND `IMAGE_FULL_NAME=alpine:3.19`

## CONFIRMATION TEMPLATE

Always use this format for confirmation:
```
I'm ready to run the {job_name} job with these parameters:
- Image: {image_name}
- Job URL: {job_url}

This will trigger a security scan on the Jenkins server. Proceed with execution?
```

## CRITICAL: NO DIRECT EXECUTION

The supervisor agent must NEVER call `trigger_job` without first:
1. Calling `get_job_info`
2. Presenting confirmation
3. Getting user approval

This ensures users understand what will be executed before any Jenkins API calls are made.