# OSCAR Agent - Master Documentation

## 🚨 CRITICAL DEPLOYMENT INFORMATION

### Never Deploy Without These Fixes

This document consolidates all critical fixes and deployment information for the OSCAR agent system. **These fixes were discovered after extensive debugging and MUST NOT BE LOST.**

---

## 🔧 Critical Issues Fixed

### 1. Variable Name Collision in slack_handler.py (CRITICAL)
**Issue**: The `context` variable was being reused, causing session IDs to be lost.

**Before (BROKEN)**:
```python
context = self.storage.get_context(thread_key)
session_id = context.get("session_id") if context else None
context = self.storage.get_context_for_query(thread_key)  # OVERWRITES context!
```

**After (FIXED)**:
```python
stored_context = self.storage.get_context(thread_key)
session_id = stored_context.get("session_id") if stored_context else None
formatted_context = self.storage.get_context_for_query(thread_key)
```

### 2. DynamoDB Table Name Inconsistency (CRITICAL)
**Issue**: Different components used different table names.
**Fix**: Standardized to `oscar-agent-context` and `oscar-agent-sessions`.

### 3. Deployment Package Structure (CRITICAL)
**Issue**: Zip file had nested paths, causing import errors.
**Fix**: Use Python to create zip file with correct structure.

### 4. Missing get_context_for_query Method (CRITICAL)
**Issue**: Method wasn't being deployed properly.
**Fix**: Ensure proper file copying and deployment.

---

## 📋 Environment Variables Required

```bash
# Core Agent Settings
OSCAR_BEDROCK_AGENT_ID=NFCKXG7OIN
OSCAR_BEDROCK_AGENT_ALIAS_ID=KNFTCYYHPT

# Slack Settings
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# DynamoDB Tables (CRITICAL - MUST BE THESE NAMES)
CONTEXT_TABLE_NAME=oscar-agent-context
SESSIONS_TABLE_NAME=oscar-agent-sessions

# TTL Settings
CONTEXT_TTL=604800
SESSION_TTL=3600
DEDUP_TTL=300

# Channel and User Settings
CHANNEL_ALLOW_LIST=C096MV7JZ0T,C09827S7CEB,C091EH1JKCL,C088XMSH4DA
AUTHORIZED_MESSAGE_SENDERS=U091B0QH1QD,W017PN2ADN0,W017VV9TD33,W017VPMPKH7,W017PKU06CC,U032Q5N0HTM

# Agent Settings
AGENT_TIMEOUT=150
AGENT_MAX_RETRIES=2
MAX_CONTEXT_LENGTH=3000
CONTEXT_SUMMARY_LENGTH=500
ENABLE_DM=true
```

---

## 🚀 Deployment Steps (FOLLOW EXACTLY)

### Step 1: Verify Environment Variables
```bash
grep "CONTEXT_TABLE_NAME=oscar-agent-context" .env
grep "SESSIONS_TABLE_NAME=oscar-agent-sessions" .env
```

### Step 2: Setup DynamoDB Tables
```bash
python setup_dynamodb_tables.py
```

### Step 3: Deploy Main Agent
```bash
./update_slack_agent.sh
```

### Step 4: Deploy Communication Handler (Optional)
```bash
./deploy_communication_handler.sh
```

### Step 5: Verify Deployment
```bash
python debug_context_preservation.py
```

---

## 🚨 Emergency Recovery Procedure

If OSCAR stops working:

### 1. Check Lambda Logs
```bash
aws logs describe-log-streams --log-group-name "/aws/lambda/oscar-supervisor-agent" --order-by LastEventTime --descending --max-items 1 --region us-east-1
```

### 2. Common Error Patterns

#### "No module named 'lambda_function'"
**Cause**: Deployment package structure is wrong
**Fix**: Re-run deployment with fixed zip creation

#### "AttributeError: 'DynamoDBStorage' object has no attribute 'get_context_for_query'"
**Cause**: Old version of storage.py deployed
**Fix**: Verify storage.py has the method and redeploy

#### "AccessDeniedException" for DynamoDB
**Cause**: IAM permissions pointing to wrong table names
**Fix**: Update IAM policy with correct table names

---

## 🔍 Context Preservation Solution

### Problem Summary
OSCAR was losing track of previous conversation turns, causing responses like "I don't see any record of sending a message previously" when users asked follow-up questions.

### Root Causes Fixed
1. **Session ID Fallback Problem**: When session IDs expired, agent created new sessions without preserving context
2. **Inconsistent Session ID Extraction**: Session IDs weren't reliably extracted from Bedrock responses
3. **Context Storage Timing**: Context was only stored after successful responses
4. **Size Limit Issues**: Context was being truncated too aggressively
5. **Poor Error Recovery**: Fallback logic didn't maintain conversation continuity

### Solution Implementation
- **Enhanced Session Management**: Smart session expiration handling with context preservation
- **Robust Context Updates**: Enhanced validation and error handling
- **Storage Layer Improvements**: Better validation and intelligent truncation
- **Configuration Updates**: Increased context limits from 3000 to 8000 characters

---

## 📊 Metrics System Simplification

### What Was Changed
Transformed from complex multi-strategy approach to clean, efficient system that serves raw data to LLMs.

### Key Improvements
1. **Agent Type Parameter Fix**: Now correctly extracted from event parameters
2. **Simplified Query Logic**: Removed ~500 lines of complex strategy execution
3. **Response Format Standardization**: Consistent structure across all agents
4. **Modular Parameter Support**: Any combination of parameters works
5. **LLM-Friendly Output**: Returns complete table entries for intelligent interpretation

### Test Results
- Direct Lambda Function Tests: 4/4 (100%) ✅
- Agent Type Parameter Tests: 6/6 (100%) ✅
- End-to-End Supervisor Routing: 3/3 (100%) ✅

---

## 🔐 Cross-Channel Context Preservation

### Problem
When OSCAR sent messages to different channels, users in those channels couldn't have follow-up conversations because no context was stored.

### Solution
Enhanced communication handler to store context for cross-channel messages:
- Stores redacted context for privacy protection
- Enables follow-up conversations in target channels
- Maintains conversation continuity across channels

### Privacy Protection
- Original user queries are redacted in cross-channel contexts
- Only bot responses are preserved for context
- Protects sensitive information from leaking between channels

---

## 🎯 Performance Analysis & Optimization

### Bedrock Agent Response Size Bottleneck
**Discovery**: Integration test queries were hanging due to large response sizes (741 KB vs 220 KB for build metrics).

**Solution**: Optimized response structure by removing verbose fields:
- Reduced response size by ~70%
- Maintained essential data for analysis
- Fixed hanging queries in Slack

### Deduplication Order Principle
**Critical Rule**: Always deduplicate before filtering to avoid losing recent passing results that override older failing results.

---

## 📁 Files Modified

### Core Files
1. **oscar-agent/slack_handler.py** - Fixed variable name collision
2. **oscar-agent/oscar_agent.py** - Fixed empty context handling
3. **oscar-agent/config.py** - Updated default table names
4. **oscar-agent/storage.py** - Added get_context_for_query method
5. **oscar-agent/communication_handler.py** - Added cross-channel context storage

### Deployment Scripts
1. **update_slack_agent.sh** - Fixed deployment package creation
2. **deploy_communication_handler.sh** - Added DynamoDB permissions
3. **setup_dynamodb_tables.py** - Automated table setup

### Configuration
1. **.env** - Updated table names
2. **IAM policies** - Updated for correct table names

---

## ✅ Verification Checklist

After deployment, verify these work:
- [ ] `@oscar hello` responds (basic functionality)
- [ ] Thread conversations maintain context
- [ ] Cross-channel messages work (if authorized)
- [ ] No "red X" errors in Slack
- [ ] CloudWatch logs show successful processing
- [ ] `python debug_context_preservation.py` passes all tests

---

## 🚨 Red Flags to Watch For

- **"No module named 'lambda_function'"** → Deployment package structure issue
- **"AttributeError: ... 'get_context_for_query'"** → Missing method or variable collision
- **"AccessDeniedException"** → Wrong table names in IAM policy
- **Bot does nothing** → Import errors or missing dependencies
- **Perpetual thinking emoji** → Response size too large for Bedrock agent

---

## 🔧 Troubleshooting Commands

```bash
# Check function status
aws lambda get-function --function-name oscar-supervisor-agent --region us-east-1

# Check latest logs
aws logs tail /aws/lambda/oscar-supervisor-agent --region us-east-1 --follow

# Test DynamoDB access
python debug_context_preservation.py

# Check IAM permissions
aws iam get-role-policy --role-name oscar-supervisor-lambda-role --policy-name DynamoDBAccess

# Test API Gateway endpoint
curl -X POST https://your-api-gateway-url/prod/slack \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test"}'
```

---

## 🎯 Success Indicators

When everything is working correctly:
- ✅ OSCAR responds to `@oscar hello`
- ✅ Context is preserved in thread conversations
- ✅ No import errors in CloudWatch logs
- ✅ DynamoDB tables show activity
- ✅ Cross-channel messages work for authorized users
- ✅ Metrics queries return accurate data
- ✅ No perpetual thinking emojis

---

## 💡 Key Learnings

1. **Always verify code before deployment** - Use verification checks
2. **Table names must be consistent** - Any mismatch breaks everything
3. **Zip file structure matters** - Use Python method, not bash `cd && zip`
4. **Test immediately after deployment** - Don't wait to discover issues
5. **Response size affects Bedrock processing** - Large responses can cause timeouts
6. **Context preservation is critical** - Users expect conversation continuity
7. **Privacy matters in cross-channel features** - Always redact sensitive information

---

## 🚀 Future Enhancements

### Monitoring
- Set up CloudWatch alarms for Lambda errors
- Monitor response sizes to prevent Bedrock timeouts
- Track context preservation success rates

### Performance
- Implement response size monitoring
- Consider pagination for large result sets
- Add caching for frequently requested queries

### Features
- Enhanced cross-channel context linking
- Improved error recovery mechanisms
- Better user feedback for long-running queries

---

**🚨 REMEMBER: These fixes took extensive debugging to discover. Don't lose them! Always refer to this document before making changes to the OSCAR system.**