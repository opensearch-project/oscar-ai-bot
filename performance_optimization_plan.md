# OSCAR Agent Performance Optimization Plan

## Current Issues Identified

### 1. **Excessive Processing Times**
- Agent queries taking 20-60 seconds
- Complex 6-step workflow for message sending
- Multiple sequential API calls (knowledge base + metrics + formatting)

### 2. **Agent Timeout Configuration**
- Current: AGENT_TIMEOUT=150 in .env
- Agent instructions show fallback to 90 seconds
- Lambda timeout is 150s but agent queries are taking 20-60s

### 3. **Complex Workflow Requirements**
- Mandatory template retrieval search
- Required metrics data collection
- User verification step (adds round-trip delay)
- Multiple function calls in sequence

## Immediate Fixes

### 1. **Update Agent Timeout Configuration**
```bash
# Update the slack agent to use consistent timeout values
./lambda_update_scripts/update_slack_agent.sh
```

### 2. **Optimize Agent Instructions**
The current workflow is too complex. We need to:
- Reduce mandatory steps
- Allow parallel processing where possible
- Simplify the verification process

### 3. **Performance Monitoring**
- Add more detailed logging to identify bottlenecks
- Monitor Bedrock agent response times
- Track individual step durations

## Recommended Changes

### 1. **Streamline Message Sending Workflow**
Instead of 6 sequential steps, use 3 parallel steps:
1. **Detect + Template Retrieval** (parallel)
2. **Data Collection + Formatting** (parallel)
3. **Send Message** (after user confirmation)

### 2. **Increase Timeouts**
- Agent timeout: 150s → 180s
- Lambda timeout: 150s → 180s
- Add buffer for complex queries

### 3. **Optimize Agent Instructions**
- Remove mandatory template search for simple messages
- Make metrics collection conditional
- Allow direct message sending for simple cases

### 4. **Add Performance Logging**
- Track each step duration
- Log bottlenecks
- Monitor agent response patterns

## Implementation Priority

1. **HIGH**: Fix timeout configurations (immediate)
2. **HIGH**: Update agent instructions to be less complex
3. **MEDIUM**: Add performance monitoring
4. **LOW**: Optimize individual components