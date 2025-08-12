# OSCAR Slack Bot Slash Commands Setup

## Overview
This guide explains how to set up slash commands for your OSCAR Slack bot for message orchestration using predefined templates.

## Available Slash Commands
- `/oscar-announce <channel> <version> [Optional: rc_number]` - Send release announcement
- `/oscar-assign-owner <channel> <version> [Optional: rc_number]` - Send release owner assignment
- `/oscar-request-owner <channel> <version> [Optional: rc_number]` - Send request for release owner
- `/oscar-rc-details <channel> <version> [Optional: rc_number]` - Send RC details
- `/oscar-missing-notes <channel> <version> [Optional: rc_number]` - Send missing release notes alert
- `/oscar-integration-test <channel> <version> [Optional: rc_number]` - Send integration test status
- `/oscar-broadcast <channel> <your_query>` - Send custom query response

## Slack App Configuration

### 1. Navigate to Slack App Settings
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Select your OSCAR bot app

### 2. Create Slash Commands
1. In the left sidebar, click **Slash Commands**
2. Click **Create New Command**

For each command, use these settings:

#### /oscar-announce
- **Command**: `/oscar-announce`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Send release announcement to channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-assign-owner
- **Command**: `/oscar-assign-owner`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Assign release owner to channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-request-owner
- **Command**: `/oscar-request-owner`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Request release owner in channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-rc-details
- **Command**: `/oscar-rc-details`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Send RC details to channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-missing-notes
- **Command**: `/oscar-missing-notes`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Send missing release notes alert to channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-integration-test
- **Command**: `/oscar-integration-test`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Send integration test status to channel`
- **Usage Hint**: `<channel> <version> [Optional: rc_number]`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

#### /oscar-broadcast
- **Command**: `/oscar-broadcast`
- **Request URL**: `https://your-domain.com/slack/events`
- **Short Description**: `Send custom query response to channel`
- **Usage Hint**: `<channel> <your_query>`
- **Escape channels, users, and links sent to your app**: ✅ (checked)

### 3. Install/Reinstall App
After adding slash commands, you need to reinstall the app:
1. Go to **Install App** in the left sidebar
2. Click **Reinstall to Workspace**
3. Authorize the new permissions

## How It Works

1. User types `/oscar-announce #releases 2.12.0 1` (with RC1) or `/oscar-announce #releases 2.12.0` (without RC)
2. The slash command handler processes the parameters and generates an agent query
3. The bot processes the query using the appropriate template and sends the formatted message
4. For `/oscar-query`, the user's custom query is processed and sent to the specified channel

## Authorization
Only authorized users (defined in `AUTHORIZED_MESSAGE_SENDERS`) can use these slash commands. Unauthorized users will see an error message.

## Channel Restrictions
- Slash commands can be used from any channel by authorized users
- Target channels (specified in the command parameter) must be in the `channel_allow_list`
- The bot will validate the target channel before sending messages

## Parameter Requirements

### Standard Commands (announce, assign-owner, request-owner, rc-details, missing-notes, integration-test)
- **channel** (required): Channel ID or name where message will be sent
- **version** (required): Release version (e.g., 2.12.0)
- **rc_number** (optional): RC number (e.g., 1 for RC1)

### Broadcast Command
- **channel** (required): Channel ID or name where response will be sent
- **your_query** (required): Custom query text to process

## Example Usage
- `/oscar-announce #releases 2.12.0 1` (with RC1)
- `/oscar-rc-details #releases 2.12.0` (without RC)
- `/oscar-integration-test #releases 2.12.0 2` (with RC2)
- `/oscar-broadcast #general send hello message to the team`

## Channel Parameter Formats
Both formats work for channel parameters:
- Channel ID: `C1234567890`
- Channel name: `#release-channel` or `release-channel`

## Common Settings
- **Request URL**: Replace `your-domain.com` with your actual domain
- **Method**: POST
- **Escape channels, users, and links**: ✅ Always checked
- **Usage Hint**: Shows parameter format to users including optional parameters

## Testing
1. Type `/oscar-announce #releases 2.12.0` in any channel
2. You should see the bot process the command and send the announcement
3. For custom queries: `/oscar-broadcast #general what is the current release status?`