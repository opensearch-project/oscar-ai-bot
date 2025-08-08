# OSCAR Communication Orchestration - Deployment Guide

## Overview

This guide provides the complete deployment process for the new communication orchestration functionality. This replaces the old communication-orchestrator approach with a more efficient, integrated solution.

## Architecture Changes

**Old Approach (communication-orchestrator/):**
- Separate orchestrator module
- Complex template management
- External dependencies

**New Approach (Integrated):**
- Hardcoded templates from templates/ directory
- Direct supervisor agent integration
- Simplified Lambda function
- Better authorization control

## Deployment Steps

### Step 1: Deploy the Communication Handler Lambda Function

```bash
# Deploy the Lambda function that handles message processing
./deploy_communication_handler.sh
```

This script will:
- Create the Lambda function with hardcoded templates
- Set up proper IAM roles and permissions
- Configure environment variables
- Test the function deployment

### Step 2: Update OSCAR Supervisor Agent

The slack handler has already been updated with:
- User authorization for 4 specific users
- Message sending request detection
- Integration with the supervisor agent

**Current authorized users (update with real Slack IDs):**
```python
AUTHORIZED_MESSAGE_SENDERS = [
    'U091B0QH1QD',  # Release Manager 1
    'W017VPMPKH7',  # Release Manager 2  
    'W017PN2ADN0',  # Release Manager 3
    'W017VV9TD33',  # Release Manager 4
]
```

### Step 3: Configure Bedrock Agent Console

Follow the detailed instructions in:
```
docs/COMMUNICATION_ORCHESTRATION_AGENT_CONFIG.md
```

Key configuration points:
1. Update supervisor agent instructions
2. Add communication-orchestration action group
3. Configure function schema
4. Test with authorized users

### Step 4: Deploy Updated Slack Handler

```bash
# Deploy the updated OSCAR agent with communication functionality
./deploy_oscar_complete.sh
```

## Testing the Deployment

### 1. Test Authorization

**With authorized user:**
```
@OSCAR send missing release notes message to the 3-2-0 release channel
```
**Expected:** Message processed and sent

**With unauthorized user:**
```
@OSCAR send missing release notes message to the 3-2-0 release channel
```
**Expected:** "❌ You are not authorized to use automated message sending functionality."

### 2. Test Message Types

```bash
# Test different message types
@OSCAR send missing release notes reminder for branch main
@OSCAR send criteria not met notification for component opensearch-security  
@OSCAR send documentation issues alert for owner @username
@OSCAR send code coverage notification for component opensearch-dashboards
@OSCAR announce release of version 2.19.0
```

### 3. Test Channel Routing

```bash
# Test automatic channel routing
@OSCAR send missing release notes message  # Should go to C096MV7JZ0T
@OSCAR send code coverage alert           # Should go to C09827S7CEB
```

## Available Message Templates

The system uses hardcoded templates from the `templates/` directory:

1. **missing_release_notes** → `templates/missing-release-notes.md`
2. **criteria_not_met** → `templates/criteria-not-met-template.md`
3. **documentation_issues** → `templates/documentation-issues-template.md`
4. **missing_code_coverage** → `templates/missing-code-coverage.md`
5. **release_announcement** → `templates/release-announcement-template.md`

## Channel Configuration

**Allowed channels:**
- `C096MV7JZ0T` - Primary release channel (3.2.0)
- `C09827S7CEB` - Build/CI channel
- `C091EH1JKCL` - Test/QA channel  
- `C088XMSH4DA` - General development channel

## User Authorization

**To update authorized users:**

1. Get Slack user IDs:
   - Go to Slack workspace
   - Click on user profile → More → Copy member ID

2. Update `oscar-agent/slack_handler.py`:
   ```python
   AUTHORIZED_MESSAGE_SENDERS = [
       'U_REAL_USER_ID_1',
       'U_REAL_USER_ID_2',
       'U_REAL_USER_ID_3',
       'U_REAL_USER_ID_4',
   ]
   ```

3. Redeploy the OSCAR agent

## Monitoring and Troubleshooting

### CloudWatch Logs

Monitor these log groups:
- `/aws/lambda/oscar-communication-handler`
- `/aws/lambda/oscar-slack-bot`

### Common Issues

1. **Authorization failures:**
   - Check user IDs in AUTHORIZED_MESSAGE_SENDERS
   - Verify Slack member ID format

2. **Channel not allowed:**
   - Update channel_allow_list in slack_handler.py
   - Update CHANNEL_ALLOW_LIST in communication_handler.py

3. **Template errors:**
   - Check template variable extraction logic
   - Verify hardcoded templates match expected format

### Debug Commands

```bash
# Test Lambda function directly
aws lambda invoke \
  --function-name oscar-communication-handler \
  --payload '{"actionGroup":"communication-orchestration","apiPath":"/send_message","parameters":[{"name":"query","value":"test message"}]}' \
  response.json

# Check function logs
aws logs tail /aws/lambda/oscar-communication-handler --follow
```

## Migration from Old System

If you have the old communication-orchestrator system:

1. **Backup old configuration:**
   ```bash
   cp -r communication-orchestrator/ communication-orchestrator-backup/
   ```

2. **Remove old imports from slack_handler.py:**
   - Remove CommunicationOrchestrator imports
   - Remove old command parsing logic

3. **Deploy new system:**
   ```bash
   ./deploy_communication_handler.sh
   ./deploy_oscar_complete.sh
   ```

4. **Test thoroughly before removing backup**

## Security Features

✅ **User Authorization:** Only 4 specific users can send messages  
✅ **Channel Restrictions:** Messages limited to pre-approved channels  
✅ **Template Safety:** All templates hardcoded, no user input  
✅ **Rate Limiting:** Slack API limits apply automatically  
✅ **Audit Trail:** All actions logged in CloudWatch  

## Performance Benefits

**New system vs old:**
- 🚀 **Faster:** Direct integration, no external dependencies
- 🔒 **Safer:** Hardcoded templates, better authorization
- 🛠️ **Simpler:** Single Lambda function, easier maintenance
- 📊 **Better monitoring:** Integrated CloudWatch logging

## Next Steps After Deployment

1. **Update user authorization** with real Slack member IDs
2. **Test all message types** with authorized users
3. **Monitor CloudWatch logs** for any issues
4. **Document any customizations** for your team
5. **Train release managers** on the new commands

## Support

For issues or questions:
1. Check CloudWatch logs for detailed error messages
2. Review the configuration guide: `docs/COMMUNICATION_ORCHESTRATION_AGENT_CONFIG.md`
3. Test individual components (Lambda function, Slack handler)
4. Verify all environment variables and permissions are correct

---

**🎉 The new communication orchestration system provides a more efficient, secure, and maintainable solution for automated release management messaging!**