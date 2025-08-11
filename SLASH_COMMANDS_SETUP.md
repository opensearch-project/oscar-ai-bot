# OSCAR Slack Bot Message Orchestration Slash Commands Setup

## Overview
This guide explains how to set up slash commands for your OSCAR Slack bot to simplify message orchestration using predefined templates.

## Available Slash Commands
- `/announce <channel_id_or_name>` - Send release announcement using release-announcement template
- `/assign-owner <channel_id_or_name>` - Send release owner assignment using release-owner-assignment template
- `/request-owner <channel_id_or_name>` - Send request for release owner using request-release-owner template
- `/rc-details <channel_id_or_name>` - Send RC details using rc-details template
- `/missing-notes <channel_id_or_name>` - Send missing release notes message using missing-release-notes template

## Slack App Configuration

### 1. Navigate to Slack App Settings
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Select your OSCAR bot app

### 2. Create Slash Commands
1. In the left sidebar, click **Slash Commands**
2. Click **Create New Command**

For each command, use these settings:

#### /announce
- **Command**: `/announce`
- **Request URL**: `https://your-lambda-url.amazonaws.com/` (same as your bot's webhook URL)
- **Short Description**: `Send release announcement to specified channel`
- **Usage Hint**: `<channel_id_or_name>`

#### /assign-owner
- **Command**: `/assign-owner`
- **Request URL**: `https://your-lambda-url.amazonaws.com/` (same as your bot's webhook URL)
- **Short Description**: `Send release owner assignment to specified channel`
- **Usage Hint**: `<channel_id_or_name>`

#### /request-owner
- **Command**: `/request-owner`
- **Request URL**: `https://your-lambda-url.amazonaws.com/` (same as your bot's webhook URL)
- **Short Description**: `Send request for release owner to specified channel`
- **Usage Hint**: `<channel_id_or_name>`

#### /rc-details
- **Command**: `/rc-details`
- **Request URL**: `https://your-lambda-url.amazonaws.com/` (same as your bot's webhook URL)
- **Short Description**: `Send RC details to specified channel`
- **Usage Hint**: `<channel_id_or_name>`

#### /missing-notes
- **Command**: `/missing-notes`
- **Request URL**: `https://your-lambda-url.amazonaws.com/` (same as your bot's webhook URL)
- **Short Description**: `Send missing release notes message to specified channel`
- **Usage Hint**: `<channel_id_or_name>`

### 3. Install/Reinstall App
After adding slash commands, you need to reinstall the app:
1. Go to **Install App** in the left sidebar
2. Click **Reinstall to Workspace**
3. Authorize the new permissions

## How It Works

1. User types `/announce #release-channel` or `/announce C1234567890`
2. The slash command handler sends a predefined message: `@oscar Send a release announcement message to channel #release-channel using the release-announcement template for the latest version.`
3. This message triggers the bot's normal mention handler
4. The bot processes the hardcoded query and your communication handler resolves the channel name/ID and sends the formatted message using the appropriate template

## Authorization
Only authorized users (defined in `AUTHORIZED_MESSAGE_SENDERS`) can use these slash commands. Unauthorized users will see an error message.

## Channel Restrictions
- Slash commands can be used from any channel by authorized users
- Target channels (specified in the command parameter) must be in the `channel_allow_list`
- The bot will validate the target channel before sending messages

## Predefined Messages
The hardcoded message orchestration templates are defined in `SlackHandler.PREDEFINED_MESSAGES`:

```python
PREDEFINED_MESSAGES = {
    "announce": "@oscar Send a release announcement message to channel {channel} using the release-announcement template for the latest version.",
    "assign_owner": "@oscar Send a release owner assignment message to channel {channel} using the release-owner-assignment template.",
    "request_owner": "@oscar Send a request for release owner message to channel {channel} using the request-release-owner template.",
    "rc_details": "@oscar Send RC details message to channel {channel} using the rc-details template for the current release candidate.",
    "missing_notes": "@oscar Send a missing release notes message to channel {channel} using the missing-release-notes template."
}
```

## Channel Parameter Requirement
All commands require a channel parameter (ID or name). Users must specify the target channel where the message should be sent. Both formats work:
- Channel ID: `C1234567890`
- Channel name: `#release-channel` or `release-channel`

## Adding More Commands
To add more slash commands:

1. Add the message template to `PREDEFINED_MESSAGES` with `{channel}` placeholder
2. Create a new handler method (e.g., `handle_criteria_command`)
3. Register it in `register_handlers()`: `self.app.command("/oscar-criteria")(self.handle_criteria_command)`
4. Configure the slash command in Slack App settings
5. Redeploy your Lambda function

## Testing
1. Type `/announce #release-channel` or `/announce C1234567890` in any channel
2. You should see an ephemeral confirmation message
3. The bot should then send the release announcement to the specified channel