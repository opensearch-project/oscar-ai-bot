# OSCAR Slack Integration Guide

This guide provides step-by-step instructions for integrating OSCAR with Slack after deploying the Lambda functions.

## Prerequisites

- OSCAR Lambda functions deployed successfully
- AWS API Gateway access
- Slack workspace admin permissions
- Slack app creation permissions

## Step 1: Create API Gateway

### 1.1 Create REST API

1. Go to AWS API Gateway Console
2. Click "Create API"
3. Choose "REST API" (not private)
4. Click "Build"
5. Configure:
   - API name: `oscar-slack-webhook`
   - Description: `Webhook endpoint for OSCAR Slack integration`
   - Endpoint Type: `Regional`
6. Click "Create API"

### 1.2 Create Resource and Method

1. In the API Gateway console, select your API
2. Click "Actions" → "Create Resource"
3. Configure:
   - Resource Name: `slack`
   - Resource Path: `/slack`
   - Enable CORS: ✓
4. Click "Create Resource"

5. Select the `/slack` resource
6. Click "Actions" → "Create Method"
7. Choose "POST" from dropdown
8. Click the checkmark

### 1.3 Configure Lambda Integration

1. In the POST method setup:
   - Integration type: `Lambda Function`
   - Use Lambda Proxy integration: ✓
   - Lambda Region: `us-east-1` (or your region)
   - Lambda Function: `oscar-supervisor-agent`
2. Click "Save"
3. Click "OK" to give API Gateway permission to invoke Lambda

### 1.4 Deploy API

1. Click "Actions" → "Deploy API"
2. Deployment stage: `[New Stage]`
3. Stage name: `prod`
4. Click "Deploy"
5. **Note the Invoke URL** (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com/prod`)

## Step 2: Configure Slack App

### 2.1 Create or Access Slack App

1. Go to https://api.slack.com/apps
2. Either:
   - Click "Create New App" → "From scratch"
   - Or select existing OSCAR app

If creating new app:
- App Name: `OSCAR`
- Workspace: Select your workspace
- Click "Create App"

### 2.2 Configure Bot Token Scopes

1. In your Slack app settings, go to "OAuth & Permissions"
2. Scroll to "Scopes" → "Bot Token Scopes"
3. Add these scopes:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `im:history` (if enabling DMs)
   - `im:read` (if enabling DMs)
   - `users:read`

### 2.3 Install App to Workspace

1. In "OAuth & Permissions", click "Install to Workspace"
2. Review permissions and click "Allow"
3. **Copy the Bot User OAuth Token** (starts with `xoxb-`)
4. Update your `.env` file:
   ```bash
   SLACK_BOT_TOKEN=xoxb-your-copied-token
   ```

### 2.4 Configure Event Subscriptions

1. Go to "Event Subscriptions"
2. Enable Events: **ON**
3. Request URL: `[Your API Gateway URL]/slack`
   - Example: `https://abc123.execute-api.us-east-1.amazonaws.com/prod/slack`
4. Wait for URL verification (should show ✓ Verified)

5. Subscribe to bot events:
   - `app_mention`
   - `message.im` (only if enabling DMs)

6. Click "Save Changes"

### 2.5 Get Signing Secret

1. Go to "Basic Information"
2. In "App Credentials", find "Signing Secret"
3. Click "Show" and copy the secret
4. Update your `.env` file:
   ```bash
   SLACK_SIGNING_SECRET=your-signing-secret
   ```

## Step 3: Update Lambda Environment Variables

After getting Slack credentials, update the Lambda function:

```bash
# Redeploy supervisor with new Slack credentials
./deploy_oscar_supervisor.sh
```

## Step 4: Test Integration

### 4.1 Invite OSCAR to Channel

1. In a Slack channel, type: `/invite @oscar`
2. Or go to channel settings and add the OSCAR app

### 4.2 Test Basic Functionality

Send these test messages:

```
@oscar hello
@oscar What is OpenSearch?
@oscar Show me test metrics
```

### 4.3 Test Direct Messages (if enabled)

1. Send a direct message to OSCAR
2. Try: `What are the current build metrics?`

## Step 5: Troubleshooting

### Common Issues

#### 1. URL Verification Failed
- **Symptom**: Slack shows "Your URL didn't respond with the expected challenge parameter"
- **Solution**: 
  - Check API Gateway deployment
  - Verify Lambda function is responding
  - Check CloudWatch logs for errors

#### 2. OSCAR Not Responding
- **Symptom**: No response to @oscar mentions
- **Solution**:
  - Check CloudWatch logs: `/aws/lambda/oscar-supervisor-agent`
  - Verify bot token and signing secret
  - Ensure app is installed to workspace

#### 3. Permission Errors
- **Symptom**: "This app doesn't have permission to do that"
- **Solution**:
  - Review bot token scopes
  - Reinstall app to workspace
  - Check channel permissions

#### 4. Bedrock Agent Errors
- **Symptom**: OSCAR responds with error messages
- **Solution**:
  - Verify Bedrock agent configuration
  - Check Lambda function has correct ARN in Bedrock action group
  - Verify IAM permissions

### Debug Commands

```bash
# Test API Gateway endpoint
curl -X POST https://your-api-gateway-url/prod/slack \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test"}'

# Test Lambda function directly
aws lambda invoke --function-name oscar-supervisor-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out result.json

# Check CloudWatch logs
aws logs tail /aws/lambda/oscar-supervisor-agent --follow
```

### Log Analysis

Monitor these CloudWatch log groups:
- `/aws/lambda/oscar-supervisor-agent`
- `/aws/apigateway/oscar-slack-webhook`

Look for:
- Slack signature verification
- Bedrock agent invocation
- DynamoDB operations
- Error messages

## Step 6: Advanced Configuration

### Enable Direct Messages

1. Update `.env`:
   ```bash
   ENABLE_DM=true
   ```

2. Redeploy supervisor:
   ```bash
   ./deploy_oscar_supervisor.sh
   ```

3. Add bot token scope: `im:read`

### Custom Response Behavior

Modify `oscar-agent/slack_handler.py` to customize:
- Response formatting
- Reaction management
- Context handling
- Error messages

### Monitoring and Analytics

Set up CloudWatch dashboards to monitor:
- Lambda invocation count
- Response times
- Error rates
- Slack event volume

## Security Considerations

1. **API Gateway**: Consider adding API keys or throttling
2. **Lambda**: Review IAM permissions regularly
3. **Slack**: Rotate bot tokens periodically
4. **Logs**: Ensure no sensitive data in CloudWatch logs

## Next Steps

After successful integration:

1. **Train Users**: Share usage examples and best practices
2. **Monitor Usage**: Set up CloudWatch alarms
3. **Iterate**: Gather feedback and improve responses
4. **Scale**: Consider additional Slack workspaces or features

## Support

For issues:
1. Check CloudWatch logs first
2. Verify all configuration steps
3. Test individual components
4. Review AWS service limits and quotas