# Communication Orchestrator for OSCAR Agent

The Communication Orchestrator is an intelligent messaging automation system designed specifically for release management workflows. It enables release managers to send contextual, AI-generated notifications to appropriate Slack channels through simple slash-like commands, eliminating the need for manual message composition and channel management.

## Problem Statement

Release managers frequently need to send routine notifications about:
- Build failures requiring immediate attention
- Security vulnerabilities (CVE checks) that need addressing
- Release reminders and task assignments
- Deployment status updates
- Test failures blocking releases

Manually crafting these messages and determining the right channels/mentions is time-consuming and error-prone. The Communication Orchestrator automates this entire workflow.

## Features

- **AI-Enhanced Message Generation**: Uses AWS Bedrock to generate contextual, professional messages
- **Template-Based System**: Pre-configured templates for common release management scenarios
- **Channel Management**: Automatic routing to appropriate channels based on message type
- **Mention Support**: Configurable mentions (@here, @channel, specific users)
- **Preview Functionality**: Preview messages before sending
- **Validation**: Context validation to ensure required information is provided

## Usage

### Available Commands

The communication orchestrator integrates with the OSCAR agent and responds to slash-like commands:

#### 1. Send Notification
```
@oscar /send_notification <message_type> [context_parameters]
```

**Examples:**
```
@oscar /send_notification build_failure build_name=main-build branch=main error_summary="Compilation failed"

@oscar /send_notification cve_check_failure component=opensearch severity=high cve_ids=CVE-2024-1234,CVE-2024-5678

@oscar /send_notification release_reminder release_version=2.12.0 release_date=2024-02-15 days_remaining=3
```

#### 2. Preview Message
```
@oscar /preview_message <message_type> [context_parameters]
```

**Example:**
```
@oscar /preview_message test_failure test_suite=integration failed_count=5 success_rate=85
```

#### 3. List Available Templates
```
@oscar /list_templates
```

### Message Types

#### 1. `build_failure`
- **Purpose**: Notify about build failures
- **Channels**: #release-engineering, #dev-alerts
- **Required Context**: `build_name`, `branch`
- **Optional Context**: `error_summary`, `timestamp`

#### 2. `cve_check_failure`
- **Purpose**: Alert about CVE security check failures
- **Channels**: #security-alerts, #release-engineering
- **Required Context**: `component`, `severity`
- **Optional Context**: `cve_ids`, `timestamp`

#### 3. `release_reminder`
- **Purpose**: Remind teams about upcoming release tasks
- **Channels**: #release-coordination, #dev-team
- **Required Context**: `release_version`
- **Optional Context**: `release_date`, `days_remaining`, `tasks`

#### 4. `deployment_status`
- **Purpose**: Update on deployment status
- **Channels**: #deployments, #release-engineering
- **Required Context**: `environment`, `status`, `version`
- **Optional Context**: `details`, `next_steps`

#### 5. `test_failure`
- **Purpose**: Notify about critical test failures
- **Channels**: #qa-alerts, #dev-team
- **Required Context**: `test_suite`, `failed_count`
- **Optional Context**: `success_rate`, `failed_tests`

## Configuration

### Channel Configuration

The system includes pre-configured channel mappings:

- **#release-engineering**: Primary channel for release notifications
- **#security-alerts**: Security-focused notifications
- **#dev-alerts**: Development team alerts
- **#qa-alerts**: Quality assurance alerts
- **#deployments**: Deployment status updates
- **#release-coordination**: Release planning and coordination
- **#dev-team**: General development notifications

### Message Templates

Templates are defined in `config.py` and include:
- Message structure with placeholders
- Target channels
- Default mentions
- Priority levels

### Customization

To add new message types or modify existing ones:

1. Update `communication-orchestrator/config.py`
2. Add new `MessageTemplate` instances
3. Configure channel permissions
4. Update validation rules in `message_generator.py`

## Architecture & Implementation

### System Architecture

The Communication Orchestrator follows a modular, layered architecture that integrates seamlessly with the existing OSCAR agent:

```
┌─────────────────────────────────────────────────────────────┐
│                    OSCAR Agent (Slack Handler)              │
├─────────────────────────────────────────────────────────────┤
│  Command Parser  │  Communication Orchestrator             │
├─────────────────────────────────────────────────────────────┤
│  Message Generator  │  Template Engine  │  Channel Router   │
├─────────────────────────────────────────────────────────────┤
│  AWS Bedrock (AI)  │  Configuration    │  Slack API        │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. **CommunicationOrchestrator** (`orchestrator.py`)
- **Purpose**: Main coordination layer that handles command processing and message distribution
- **Responsibilities**:
  - Validates incoming commands and context
  - Coordinates between message generation and channel routing
  - Manages bulk message sending to multiple channels
  - Handles error reporting and success tracking
- **Key Methods**:
  - `send_notification()`: Orchestrates the entire message sending process
  - `preview_message()`: Generates message previews without sending
  - `list_available_templates()`: Returns available templates and configurations

#### 2. **MessageGenerator** (`message_generator.py`)
- **Purpose**: AI-powered message generation with template processing
- **Responsibilities**:
  - Template variable substitution with context data
  - AI enhancement using AWS Bedrock (Claude 3.5 Haiku)
  - Fallback message generation for reliability
  - Context validation and error handling
- **AI Integration**:
  - Uses AWS Bedrock runtime API
  - Employs Claude 3.5 Haiku for professional message enhancement
  - Implements fallback templates when AI is unavailable
  - Configurable AI enhancement (can be disabled)

#### 3. **Configuration System** (`config.py`)
- **Purpose**: Centralized configuration management for templates and channels
- **Data Structures**:
  - `MessageTemplate`: Dataclass defining message structure, channels, mentions, and priority
  - `CommunicationConfig`: Main configuration class with template and channel management
- **Features**:
  - Template-to-channel mapping
  - Permission validation (which channels can receive which message types)
  - Default mention configuration per template
  - Priority levels for different message types

#### 4. **Command Parser** (`orchestrator.py`)
- **Purpose**: Parses slash-like commands from Slack messages
- **Supported Patterns**:
  - `/send_notification <type> [params]`
  - `/preview_message <type> [params]`
  - `/list_templates`
- **Parameter Parsing**:
  - Key-value pairs: `build_name=main-build branch=main`
  - JSON-like input: `{"build_name": "main-build", "branch": "main"}`

### Message Processing Flow

```
1. User Input
   │
   ├─ "@oscar /send_notification build_failure build_name=main-build"
   │
2. Command Detection (SlackHandler)
   │
   ├─ parse_communication_command() identifies command type
   │
3. Orchestrator Processing
   │
   ├─ Validate message type and context
   ├─ Determine target channels
   ├─ Generate message content
   │
4. Message Generation
   │
   ├─ Apply template substitution
   ├─ Enhance with AI (optional)
   ├─ Add mentions and formatting
   │
5. Channel Distribution
   │
   ├─ Send to each configured channel
   ├─ Track success/failure per channel
   ├─ Handle Slack API rate limits
   │
6. Response Generation
   │
   └─ Report results back to user
```

### Integration with OSCAR Agent

The Communication Orchestrator integrates with OSCAR through the `SlackHandler` class:

```python
# In oscar-agent/slack_handler.py
def _process_message(self, ...):
    # Check if this is a communication orchestrator command
    comm_command = parse_communication_command(text)
    if comm_command:
        self._handle_communication_command(comm_command, ...)
        return
    
    # Continue with normal OSCAR agent processing
    ...
```

**Integration Benefits**:
- Uses existing Slack client and authentication
- Leverages OSCAR's error handling and logging
- Maintains consistent user experience
- No additional Lambda functions or infrastructure required

### Data Flow & State Management

#### Template Processing
```python
MessageTemplate(
    name="build_failure",
    template="🚨 **Build Failure** 🚨\n\nBuild: {build_name}\nBranch: {branch}",
    channels=["#release-engineering", "#dev-alerts"],
    mentions=["@here"],
    priority="high"
)
```

#### Context Validation
```python
# Required fields per message type
required_fields = {
    "build_failure": ["build_name", "branch"],
    "cve_check_failure": ["component", "severity"],
    # ...
}
```

#### AI Enhancement Process
```python
# 1. Template substitution
message = template.format(**context)

# 2. AI enhancement (if enabled)
if context.get('use_ai_enhancement', True):
    enhanced_message = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-5-haiku-20241022-v1:0",
        body=enhancement_prompt
    )

# 3. Fallback handling
return enhanced_message or original_message
```

## Technical Implementation Details

### Message Template System

Templates use Python's `str.format()` with special handling for complex data types:

```python
# List formatting
if 'tasks' in context and isinstance(context['tasks'], list):
    formatted_context['task_list'] = '\n'.join([f"- {task}" for task in context['tasks']])

# CVE ID formatting  
if 'cve_ids' in context and isinstance(context['cve_ids'], list):
    formatted_context['cve_ids'] = ', '.join(context['cve_ids'])
```

### AI Enhancement Pipeline

The AI enhancement process follows a structured approach:

1. **Prompt Engineering**: Creates context-aware prompts for message improvement
2. **Model Invocation**: Uses AWS Bedrock with Claude 3.5 Haiku
3. **Response Processing**: Extracts and validates AI-generated content
4. **Fallback Handling**: Returns original template if AI fails

```python
def _create_enhancement_prompt(self, message, message_type, context):
    return f"""You are helping to improve an automated notification message for a software release management team.

Message Type: {message_type}
Current Message: {message}
Additional Context: {json.dumps(context, indent=2)}

Please improve this message by:
1. Making it more professional and clear
2. Adding relevant technical details if missing
3. Ensuring the tone is appropriate for the urgency level
4. Keeping it concise but informative
5. Maintaining any existing formatting and structure

Return only the improved message, no explanations or additional text."""
```

### Channel Permission System

Channel permissions are enforced through a mapping system:

```python
channel_configs = {
    "#release-engineering": {
        "allowed_message_types": ["build_failure", "cve_check_failure", "deployment_status"],
        "default_mention": "@here"
    },
    "#security-alerts": {
        "allowed_message_types": ["cve_check_failure"],
        "default_mention": "@channel"
    }
}
```

### Error Handling Strategy

The system implements multiple layers of error handling:

#### 1. **Validation Layer**
```python
def validate_message_context(self, message_type, context):
    errors = []
    required = required_fields.get(message_type, [])
    for field in required:
        if field not in context or not context[field]:
            errors.append(f"Missing required field: {field}")
    return errors
```

#### 2. **AI Fallback Layer**
```python
try:
    enhanced_message = self._enhance_with_ai(message, message_type, context)
    return enhanced_message
except Exception as e:
    logger.error(f"AI enhancement failed: {e}")
    return message  # Return original template
```

#### 3. **Channel-Level Error Tracking**
```python
results = []
for channel in target_channels:
    try:
        response = self.slack_client.chat_postMessage(channel=channel, text=message)
        results.append({"channel": channel, "success": True, "message_ts": response["ts"]})
    except SlackApiError as e:
        results.append({"channel": channel, "success": False, "error": str(e)})
```

### Performance Considerations

#### AI Response Time
- **Typical Response**: 2-3 seconds for AI enhancement
- **Timeout Handling**: 30-second timeout with fallback to templates
- **Optimization**: AI enhancement can be disabled for faster responses

#### Slack API Rate Limiting
- **Rate Limit**: 1 message per second per channel (Slack limitation)
- **Handling**: Sequential sending to multiple channels
- **Retry Logic**: Exponential backoff for rate limit errors

#### Memory Usage
- **Templates**: Loaded once at initialization
- **Context**: Minimal memory footprint per request
- **AI Responses**: Streamed processing to minimize memory usage

### Security and Permissions

#### Access Control
```python
def is_channel_allowed_for_template(self, channel, template_name):
    channel_config = self.channel_configs.get(channel, {})
    allowed_types = channel_config.get("allowed_message_types", [])
    return template_name in allowed_types
```

#### Input Validation
- **Context Sanitization**: All user inputs are validated against expected schemas
- **Template Injection Prevention**: No dynamic template creation from user input
- **Channel Validation**: Only pre-configured channels are accessible

#### AWS Security
- **IAM Permissions**: Uses existing OSCAR agent permissions for Bedrock
- **Encryption**: All data encrypted in transit (HTTPS/TLS)
- **Logging**: Comprehensive audit trail in CloudWatch

### Extensibility & Customization

#### Adding New Message Types
1. Define new `MessageTemplate` in `config.py`
2. Add validation rules in `message_generator.py`
3. Update channel permissions as needed
4. No code changes required in core orchestrator

#### Custom AI Prompts
```python
# Extend MessageGenerator for custom prompts
class CustomMessageGenerator(MessageGenerator):
    def _create_enhancement_prompt(self, message, message_type, context):
        if message_type == "custom_type":
            return custom_prompt_template
        return super()._create_enhancement_prompt(message, message_type, context)
```

#### Integration Points
- **Webhooks**: Can be extended to receive external triggers
- **CI/CD Integration**: Template context can be populated from build systems
- **Monitoring**: Built-in logging supports external monitoring systems

## Testing & Validation

### Test Suite (`test_orchestrator.py`)

The system includes comprehensive tests covering:

#### 1. **Configuration Testing**
```python
def test_configuration():
    templates = communication_config.get_available_templates()
    assert len(templates) == 5
    
    build_template = communication_config.get_template("build_failure")
    assert build_template.priority == "high"
    assert "#release-engineering" in build_template.channels
```

#### 2. **Message Generation Testing**
```python
def test_message_generation():
    context = {"build_name": "test-build", "branch": "main", "use_ai_enhancement": False}
    message = generator.generate_message("build_failure", context)
    assert "🚨 **Build Failure Alert** 🚨" in message
    assert "test-build" in message
```

#### 3. **Command Parsing Testing**
```python
def test_command_parsing():
    cmd = "@oscar /send_notification build_failure build_name=main-build branch=main"
    result = parse_communication_command(cmd)
    assert result[0] == "send_notification"
    assert result[1]["message_type"] == "build_failure"
```

#### 4. **Integration Testing**
```python
def test_orchestrator_mock():
    mock_slack_client = Mock()
    orchestrator = CommunicationOrchestrator(mock_slack_client)
    result = orchestrator.preview_message("build_failure", context)
    assert result["success"] == True
```

### Running Tests
```bash
cd communication-orchestrator
python test_orchestrator.py
```

## Deployment & Operations

### Deployment Checklist
1. ✅ Include `communication-orchestrator/` in Lambda package
2. ✅ Verify Slack bot permissions (`chat:write`, `channels:read`)
3. ✅ Confirm AWS Bedrock access for AI enhancement
4. ✅ Test with `/list_templates` command
5. ✅ Validate channel access with preview commands

### Monitoring & Observability

#### CloudWatch Logs
```python
# Key log patterns to monitor
logger.info(f"Successfully sent {message_type} notification to {channel}")
logger.error(f"Failed to send message to {channel}: {error_msg}")
logger.warning(f"AI enhancement failed: {e}")
```

#### Metrics to Track
- **Message Success Rate**: Percentage of successfully sent messages
- **AI Enhancement Usage**: How often AI enhancement is used vs. fallback
- **Channel Distribution**: Which channels receive the most notifications
- **Response Times**: Time from command to message delivery

#### Alerting Recommendations
- Alert on high failure rates (>10% failed messages)
- Monitor AI enhancement failures
- Track unusual spikes in notification volume

### Troubleshooting Guide

#### Common Issues & Solutions

1. **"Template not found" errors**
   - Check template name spelling in command
   - Verify template exists in `config.py`

2. **"Channel not allowed" errors**
   - Verify channel permissions in `channel_configs`
   - Ensure bot is added to target channels

3. **AI enhancement timeouts**
   - Check AWS Bedrock service status
   - Verify IAM permissions for Bedrock access
   - Consider disabling AI enhancement temporarily

4. **Slack API errors**
   - Verify bot token validity
   - Check rate limiting (1 msg/sec per channel)
   - Ensure bot has required permissions

### Performance Optimization

#### For High-Volume Usage
```python
# Disable AI enhancement for faster responses
context = {
    "build_name": "main-build",
    "branch": "main", 
    "use_ai_enhancement": False  # Faster processing
}
```

#### Batch Processing
```python
# Send to multiple channels efficiently
channels = ["#release-engineering", "#dev-alerts"]
result = orchestrator.send_notification(
    message_type="build_failure",
    context=context,
    channels=channels  # Override template defaults
)
```

## Future Enhancements

### Planned Features
1. **Scheduled Messaging**: Time-based message delivery
2. **Approval Workflows**: Multi-step approval for sensitive notifications
3. **Custom Templates**: Dynamic template creation via Slack interface
4. **CI/CD Integration**: Direct triggers from build systems
5. **Analytics Dashboard**: Message effectiveness tracking
6. **Multi-Workspace Support**: Cross-workspace notification capabilities

### Extension Architecture
The system is designed for easy extension:

```python
# Example: Adding webhook support
class WebhookOrchestrator(CommunicationOrchestrator):
    def handle_webhook(self, payload):
        message_type = payload.get('type')
        context = payload.get('context', {})
        return self.send_notification(message_type, context)
```

### Integration Opportunities
- **Jira Integration**: Automatic ticket creation with notifications
- **PagerDuty Integration**: Escalation for critical alerts
- **Metrics Collection**: Integration with monitoring systems
- **Custom Dashboards**: Real-time notification analytics

## Examples

### Build Failure Notification
```
@oscar /send_notification build_failure build_name=opensearch-main branch=main error_summary="Unit tests failed in security module"
```

**Generated Message:**
```
@here

🚨 **Build Failure Alert** 🚨

A critical build has failed and requires immediate attention.

**Details:**
- Build: opensearch-main
- Branch: main
- Failure Time: 2024-02-08 14:30:00 UTC
- Error: Unit tests failed in security module

Please investigate and resolve this issue as soon as possible.
```

### CVE Check Failure
```
@oscar /send_notification cve_check_failure component=opensearch-security severity=critical cve_ids=CVE-2024-1234
```

**Generated Message:**
```
@channel

🔒 **Security Alert - CVE Check Failed** 🔒

**Critical security vulnerabilities detected!**

**Details:**
- Component: opensearch-security
- CVE IDs: CVE-2024-1234
- Severity: critical
- Scan Time: 2024-02-08 14:30:00 UTC

**Action Required:** Please review and address these security issues immediately.
```

## Integration with OSCAR Agent

The communication orchestrator is fully integrated with the existing OSCAR agent infrastructure:

- Uses the same Slack client and authentication
- Leverages existing configuration management
- Integrates with the message processing pipeline
- Maintains consistency with OSCAR's response patterns

This ensures a seamless experience for users who are already familiar with the OSCAR agent interface.