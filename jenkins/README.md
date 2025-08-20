# Jenkins Integration for OSCAR

Secure Jenkins job execution through conversational AI with mandatory confirmation workflow and user authorization.

## 🚀 Quick Start
1. Configure environment variables in `.env`
2. Deploy Lambda function: `./deployment/update_lambda.sh`
3. Update Jenkins agent instructions in AWS Bedrock Console (see `AGENT_INSTRUCTIONS_FOR_BEDROCK_CONSOLE.md`)
4. Test with: "Run docker scan on alpine:3.19"

## 📚 Documentation
See `JENKINS_INTEGRATION_GUIDE.md` for comprehensive documentation including:
- Architecture overview
- Security features
- Workflow examples
- Configuration guide
- Troubleshooting

## 🔐 Security Features
- **User Authorization**: Only users in `AUTHORIZED_MESSAGE_SENDERS` can execute jobs
- **Mandatory Confirmation**: Two-phase workflow (info → confirm → execute)
- **Parameter Validation**: `confirmed=true` required for job execution
- **Audit Trail**: Complete logging of all operations

## 🛠️ Key Files
- `lambda_function.py` - Main Lambda handler with confirmation system
- `jenkins_client.py` - Jenkins API client
- `job_definitions.py` - Job registry and parameter validation
- `AGENT_INSTRUCTIONS_FOR_BEDROCK_CONSOLE.md` - Copy to Bedrock console
- `JENKINS_INTEGRATION_GUIDE.md` - Complete documentation

## 📋 Available Functions

| Function | Purpose | Parameters | Example Usage |
|----------|---------|------------|---------------|
| `get_job_info` | Get job details | `job_name` (optional) | "what params does docker-scan need?" |
| `trigger_job` | Execute Jenkins job | `job_name`, `confirmed`, job params | Requires confirmation workflow |
| `list_jobs` | List available jobs | None | "what jobs are available?" |
| `test_connection` | Jenkins health check | None | "is Jenkins working?" |

## 🧪 Testing

### Direct Lambda Testing
```bash
# Test get_job_info
aws lambda invoke --function-name oscar-jenkins-agent \
  --payload '{"function":"get_job_info","parameters":[{"name":"job_name","value":"docker-scan"}]}' \
  response.json

# Test trigger_job with confirmation
aws lambda invoke --function-name oscar-jenkins-agent \
  --payload '{"function":"trigger_job","parameters":[{"name":"job_name","value":"docker-scan"},{"name":"IMAGE_FULL_NAME","value":"alpine:3.19"},{"name":"confirmed","value":"true"}]}' \
  response.json
```

### End-to-End Testing
1. Send message in Slack: "Run docker scan on alpine:3.19"
2. Verify agent asks for confirmation
3. Reply "yes" and verify job executes

The Jenkins integration is ready for production use with robust confirmation workflow! 🎉