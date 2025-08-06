# OSCAR Slack Deployment Guide

This guide provides complete step-by-step instructions for deploying OSCAR to Slack after your metrics agents are working.

## Prerequisites

✅ **Completed Steps:**
- Metrics Lambda functions deployed and working
- Bedrock agents configured and responding
- All permissions properly set

## Step 1: Deploy All OSCAR Components

### 1.1 Deploy Metrics Agents with Permissions

The updated deployment script now automatically adds Bedrock permissions:

```bash
# Deploy metrics agents (includes automatic permission setup)
./deploy_metrics.sh
```

This script now:
- Deploys all 4 metrics Lambda functions
- Automatically adds Bedrock agent permissions
- No need to run separate permissions script

### 1.2 Deploy Supervisor Agent

```bash
# Deploy the main OSCAR supervisor agent
./deploy_oscar_supervisor.sh
```

### 1.3 Verify Deployments

```bash
# Test supervisor
aws lambda invoke --function-name oscar-supervisor-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json

# Test metrics agent
aws lambda invoke --function-name oscar-test-metrics-agent-new \
  --payload '{"function": "test_basic"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json
```

## Step 2: Create API Gateway for Slack Webhook

### 2.1 Create REST API

1. Go to **AWS API Gateway Console**
2. Click **"Create API"**
3. Choose **"REST API"** (not private)
4. Click **"Build"**
5. Configure:
   - **API name:** `oscar-slack-webhook`
   - **Description:** `Webhook endpoint for OSCAR Slack integration`
   - **Endpoint Type:** `Regional`
6. Click **"Create API"**

### 2.2 Create Resource and Method

1. In the API Gateway console, select your API
2. Click **"Actions"** → **"Create Resource"**
3. Configure:
   - **Resource Name:** `slack`
   - **Resource Path:** `/slack`
   - **Enable CORS:** ✓
4. Click **"Create Resource"**

5. Select the `/slack` resource
6. Click **"Actions"** → **"Create Method"**
7. Choose **"POST"** from dropdown
8. Click the checkmark

### 2.3 Configure Lambda Integration

1. In the POST method setup:
   - **Integration type:** `Lambda Function`
   - **Use Lambda Proxy integration:** ✓
   - **Lambda Region:** `us-east-1`
   - **Lambda Function:** `oscar-supervisor-agent`
2. Click **"Save"**
3. Click **"OK"** to give API Gateway permission to invoke Lambda

### 2.4 Deploy API

1. Click **"Actions"** → **"Deploy API"**
2. **Deployment stage:** `[New Stage]`
3. **Stage name:** `prod`
4. Click **"Deploy"**
5. **📝 IMPORTANT:** Copy the **Invoke URL** (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com/prod`)

## Step 3: Configure Slack App

### 3.1 Create or Access Slack App

1. Go to https://api.slack.com/apps
2. Either:
   - Click **"Create New App"** → **"From scratch"**
   - Or select existing OSCAR app

If creating new app:
- **App Name:** `OSCAR`
- **Workspace:** Select your workspace
- Click **"Create App"**

### 3.2 Configure Bot Token Scopes

1. In your Slack app settings, go to **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Add these scopes:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `im:history` (if enabling DMs)
   - `im:read` (if enabling DMs)
   - `users:read`
   - `reactions:read`
   - `reactions:write`

### 3.3 Install App to Workspace

1. In **"OAuth & Permissions"**, click **"Install to Workspace"**
2. Review permissions and click **"Allow"**
3. **📝 IMPORTANT:** Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### 3.4 Get Signing Secret

1. Go to **"Basic Information"**
2. In **"App Credentials"**, find **"Signing Secret"**
3. Click **"Show"** and copy the secret

### 3.5 Update Environment Variables

Update your `.env` file with Slack credentials:

```bash
# Add these to your .env file
SLACK_BOT_TOKEN=xoxb-your-copied-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
ENABLE_DM=false  # Set to true if you want DM support
```

### 3.6 Configure Event Subscriptions

1. Go to **"Event Subscriptions"**
2. **Enable Events:** **ON**
3. **Request URL:** `[Your API Gateway URL]/slack`
   - Example: `https://abc123.execute-api.us-east-1.amazonaws.com/prod/slack`
4. Wait for URL verification (should show ✓ **Verified**)

5. **Subscribe to bot events:**
   - `app_mention`
   - `message.im` (only if enabling DMs)

6. Click **"Save Changes"**

## Step 4: Redeploy Supervisor with Slack Credentials

After updating your `.env` file with Slack credentials:

```bash
# Redeploy supervisor with new Slack credentials
./deploy_oscar_supervisor.sh
```

## Step 5: Test Slack Integration

### 5.1 Invite OSCAR to Channel

1. In a Slack channel, type: `/invite @oscar`
2. Or go to channel settings and add the OSCAR app

### 5.2 Test Basic Functionality

Send these test messages in the channel:

```
@oscar hello
@oscar What is OpenSearch?
@oscar Show me test metrics for the last 7 days
@oscar What are the current build metrics?
@oscar Tell me about release readiness
```

### 5.3 Test Direct Messages (if enabled)

If you set `ENABLE_DM=true`:

1. Send a direct message to OSCAR
2. Try: `What are the current deployment metrics?`

## Step 6: Troubleshooting

### Common Issues and Solutions

#### 1. URL Verification Failed
**Symptom:** Slack shows "Your URL didn't respond with the expected challenge parameter"

**Solutions:**
- Check API Gateway deployment status
- Verify Lambda function is responding
- Check CloudWatch logs: `/aws/lambda/oscar-supervisor-agent`

#### 2. OSCAR Not Responding
**Symptom:** No response to @oscar mentions

**Solutions:**
- Check CloudWatch logs: `/aws/lambda/oscar-supervisor-agent`
- Verify bot token and signing secret in `.env`
- Ensure app is installed to workspace
- Check API Gateway logs

#### 3. Permission Errors
**Symptom:** "This app doesn't have permission to do that"

**Solutions:**
- Review bot token scopes in Slack app settings
- Reinstall app to workspace
- Check channel permissions

#### 4. Bedrock Agent Errors
**Symptom:** OSCAR responds with error messages

**Solutions:**
- Verify Bedrock agent configuration
- Check Lambda function ARNs in Bedrock action groups
- Verify IAM permissions
- Test individual metrics functions

### Debug Commands

```bash
# Test API Gateway endpoint
curl -X POST https://your-api-gateway-url/prod/slack \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test"}'

# Test Lambda function directly
aws lambda invoke --function-name oscar-supervisor-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 result.json && cat result.json

# Check CloudWatch logs
aws logs tail /aws/lambda/oscar-supervisor-agent --region us-east-1 --follow
```

### Log Analysis

Monitor these CloudWatch log groups:
- `/aws/lambda/oscar-supervisor-agent`
- `/aws/lambda/oscar-test-metrics-agent-new`
- `/aws/lambda/oscar-build-metrics-agent-new`
- `/aws/lambda/oscar-release-metrics-agent-new`
- `/aws/lambda/oscar-deployment-metrics-agent-new`
- `/aws/apigateway/oscar-slack-webhook`

Look for:
- Slack signature verification
- Bedrock agent invocation
- DynamoDB operations
- Error messages

## Step 7: Verification Checklist

✅ **Deployment Verification:**
- [ ] All 4 metrics Lambda functions deployed
- [ ] Supervisor Lambda function deployed
- [ ] API Gateway created and deployed
- [ ] Slack app configured with proper scopes
- [ ] Bot token and signing secret in `.env`
- [ ] Event subscriptions configured

✅ **Functionality Testing:**
- [ ] URL verification successful
- [ ] @oscar mentions work in channels
- [ ] OSCAR responds to basic queries
- [ ] Metrics queries return data
- [ ] Reactions appear on messages (thinking_face, white_check_mark)
- [ ] Direct messages work (if enabled)

## Step 8: Usage Examples

Once deployed, users can interact with OSCAR like this:

```
# General queries
@oscar What is OpenSearch?
@oscar How do I configure security?

# Metrics queries
@oscar Show me test metrics for the last 7 days
@oscar What are the current build success rates?
@oscar Tell me about release readiness for production
@oscar Show deployment metrics for the OpenSearch service

# Context-aware conversations
@oscar What are the test coverage trends?
@oscar Can you explain those results in more detail?
@oscar What should we focus on improving?
```

## Step 9: Monitoring and Maintenance

### Set Up CloudWatch Alarms

```bash
# Example: Monitor Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name "OSCAR-Supervisor-Errors" \
  --alarm-description "Monitor OSCAR supervisor Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=oscar-supervisor-agent \
  --evaluation-periods 2
```

### Regular Maintenance

- **Weekly:** Check CloudWatch logs for errors
- **Monthly:** Review and rotate Slack tokens if needed
- **Quarterly:** Update dependencies and redeploy

## Security Considerations

1. **API Gateway:** Consider adding API keys or throttling
2. **Lambda:** Review IAM permissions regularly
3. **Slack:** Rotate bot tokens periodically
4. **Logs:** Ensure no sensitive data in CloudWatch logs

## Next Steps

After successful deployment:

1. **Train Users:** Share usage examples and best practices
2. **Monitor Usage:** Set up CloudWatch dashboards
3. **Iterate:** Gather feedback and improve responses
4. **Scale:** Consider additional Slack workspaces or features

## Support

For issues:
1. Check CloudWatch logs first
2. Verify all configuration steps
3. Test individual components
4. Review AWS service limits and quotas

---

**🎉 Congratulations!** OSCAR is now deployed and ready to use in Slack!