# OSCAR Dual-Agent Refactoring Summary

## Overview
This document summarizes the comprehensive refactoring of OSCAR to implement a dual-agent architecture that separates privileged and limited functionality based on user permissions. This approach eliminates complex authorization logic in action groups and provides true security isolation.

## Architecture Changes

### Dual-Agent Security Model
- **Privileged Agent**: Full access to all action groups (communication, jenkins, metrics, knowledge base)
- **Limited Agent**: Access only to knowledge base and metrics action groups
- **User Routing**: Users are routed to appropriate agent based on their privilege level

## Files Modified

### 1. **oscar-agent/config.py**
**Changes:**
- Added dual-agent configuration variables:
  - `oscar_limited_bedrock_agent_id` - Limited agent ID
  - `oscar_limited_bedrock_agent_alias_id` - Limited agent alias ID
- Updated authorization configuration:
  - Renamed `authorized_message_senders` to `dm_authorized_users` (for DM access)
  - Added `fully_authorized_users` (for privileged agent access)
- Maintained backward compatibility with existing configuration

**Effect:** Enables dual-agent routing and clarifies user permission levels

### 2. **oscar-agent/bedrock/agent_invoker.py**
**Changes:**
- Updated constructor to store both privileged and limited agent configurations
- Modified `create_agent_request()` to accept `privilege` parameter and route to appropriate agent
- Updated `invoke_agent()` to pass privilege parameter through the call chain
- Enhanced logging to show both agent configurations

**Effect:** Core routing logic that directs users to appropriate agent based on privileges

### 3. **oscar-agent/bedrock/main_agent.py**
**Changes:**
- Added `privilege` parameter to `query()` method signature
- Updated call to `query_processor.process_query()` to pass privilege parameter

**Effect:** Passes privilege information through the agent orchestration layer

### 4. **oscar-agent/bedrock/query_processor.py**
**Changes:**
- Added `privilege` parameter to `process_query()` method signature
- Updated all calls to `bedrock_agent.invoke_agent()` to pass privilege parameter
- Maintained all existing retry and fallback logic

**Effect:** Ensures privilege information reaches the actual agent invocation

### 5. **oscar-agent/slack_handler/message_processor.py**
**Changes:**
- Removed `AuthorizationManager` import and initialization
- Added `is_fully_authorized_user()` method to check user privileges
- Removed authorization checks for message sending requests
- Updated agent query to include privilege parameter
- Simplified message processing flow by removing authorization barriers

**Effect:** Streamlined message processing with privilege-based agent routing instead of authorization blocking

### 6. **oscar-agent/slack_handler/timeout_handler.py**
**Changes:**
- Added `privilege` parameter to `query_agent_with_timeout()` method signature
- Updated call to `oscar_agent.query()` to pass privilege parameter

**Effect:** Maintains privilege information through timeout handling

### 7. **oscar-agent/slack_handler/constants.py**
**Changes:**
- Renamed `AUTHORIZED_MESSAGE_SENDERS` to `DM_AUTHORIZED_USERS`
- Added `FULLY_AUTHORIZED_USERS` constant
- Updated imports from config to use new variable names

**Effect:** Clarifies different authorization levels and their purposes

### 8. **oscar-agent/slack_handler/event_handlers.py**
**Changes:**
- Removed `AuthorizationManager` import and initialization
- Updated DM authorization check to use new constants directly
- Simplified authorization logic for direct message handling

**Effect:** Cleaner DM access control without unnecessary abstraction layers

### 9. **oscar-agent/slack_handler/slash_commands.py**
**Changes:**
- Removed `AuthorizationManager` import and initialization
- Removed authorization checks from slash command handlers
- Simplified slash command processing flow

**Effect:** Slash commands now rely on agent-level security instead of pre-processing authorization

### 10. **oscar-agent/app.py**
**Changes:**
- Removed entire `handle_authentication_action_group()` function
- Removed `handle_user_authorization_check()` function
- Removed `create_bedrock_response()` function
- Removed authentication action group routing from `lambda_handler()`
- Simplified main handler logic

**Effect:** Eliminated obsolete authentication system that's now handled by dual-agent routing

### 11. **jenkins/lambda_function.py**
**Changes:**
- Removed `authorized` parameter from `handle_trigger_job()` function
- Removed all authorization validation logic (50+ lines of code)
- Updated parameter filtering to exclude only `job_name` and `confirmed`
- Updated logging messages to reflect dual-agent routing
- Simplified function signature and documentation

**Effect:** Cleaner Jenkins integration that relies on agent-level security instead of parameter-based authorization

### 12. **jenkins/schemas/jenkins_action_group.json**
**Changes:**
- Removed `authorized` parameter definition from trigger_job function schema
- Simplified required parameters list

**Effect:** Cleaner action group schema without redundant authorization parameters

### 13. **jenkins/config.py**
**Changes:**
- Removed `_load_authorized_senders()` method
- Removed `is_user_authorized()` method
- Removed `authorized_message_senders` attribute
- Added comment explaining that authorization is now handled by dual-agent routing

**Effect:** Eliminated redundant authorization logic since Jenkins Lambda is only accessible through privileged agent

### 14. **oscar-agent/slack_handler/authorization.py**
**Status:** DELETED
**Original Content:** 
- `AuthorizationManager` class with message sending detection
- User authorization checking methods

**Effect:** Eliminated unnecessary abstraction layer - authorization now handled by agent routing

## Key Benefits

### 1. **True Security Isolation**
- Limited users cannot access privileged functions at all (not just blocked by parameters)
- Privileged functions are completely unavailable to the limited agent
- No risk of authorization bypass through parameter manipulation

### 2. **Simplified Architecture**
- Removed complex authorization logic from action groups
- Eliminated parameter-based security checks
- Cleaner agent instructions focused on capabilities rather than restrictions

### 3. **Better Maintainability**
- Single point of privilege checking in message processor
- No authorization logic scattered across multiple action groups
- Easier to add new privileged or limited features

### 4. **Enhanced Performance**
- No authorization checks during action group execution
- Reduced parameter passing overhead
- Faster response times for all operations

### 5. **Improved User Experience**
- Clear separation between what different user types can do
- No confusing "access denied" messages during conversations
- Limited users get appropriate responses about unavailable features

## Security Model

### User Categories
1. **Fully Authorized Users** (`FULLY_AUTHORIZED_USERS`)
   - Access to privileged agent with all capabilities
   - Can execute Jenkins jobs, send messages, access all features
   
2. **DM Authorized Users** (`DM_AUTHORIZED_USERS`)
   - Can direct message the bot
   - Access to limited agent (knowledge base and metrics only)
   
3. **Channel Users**
   - Can interact in allowed channels
   - Access to limited agent (knowledge base and metrics only)

### Agent Routing Logic
```
User Request → Check Privileges → Route to Agent
├── Fully Authorized → Privileged Agent (all action groups)
└── Others → Limited Agent (knowledge base + metrics only)
```

## Configuration Changes

### New Environment Variables
```bash
# Dual-agent configuration
OSCAR_LIMITED_BEDROCK_AGENT_ID=your-limited-agent-id
OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_ID=your-limited-agent-alias

# Updated authorization
FULLY_AUTHORIZED_USERS=U123,U456,U789  # Users with full privileges
DM_AUTHORIZED_USERS=U123,U456,U789,U999  # Users who can DM (may overlap)
```

### Deprecated Environment Variables
```bash
# No longer used (but won't break if present)
AUTHORIZED_MESSAGE_SENDERS  # Replaced by FULLY_AUTHORIZED_USERS + DM_AUTHORIZED_USERS
```

## Testing Verification

### Functionality Preserved
- ✅ Slack message processing with context retention
- ✅ Jenkins job execution with confirmation workflow
- ✅ Cross-channel message sending
- ✅ Slash command processing
- ✅ Metrics querying and knowledge base access
- ✅ User privilege checking and routing

### Security Enhancements
- ✅ Limited users cannot access Jenkins functions
- ✅ Limited users cannot send cross-channel messages
- ✅ Privileged users maintain full functionality
- ✅ No authorization bypass possible through parameter manipulation

## Migration Notes

### Backward Compatibility
- Existing `AUTHORIZED_MESSAGE_SENDERS` configuration will be ignored but won't cause errors
- All existing functionality preserved for authorized users
- No breaking changes to external interfaces

### Deployment Requirements
1. Create limited supervisor agent in AWS Bedrock Console
2. Configure limited agent without communication and jenkins action groups
3. Update environment variables with new agent IDs
4. Deploy updated code
5. Test both privileged and limited user scenarios

## Future Enhancements

### Potential Improvements
1. **Granular Permissions**: Different privilege levels for different features
2. **Dynamic Routing**: Route based on query content rather than just user
3. **Audit Logging**: Enhanced logging of privilege-based routing decisions
4. **Admin Interface**: Web interface for managing user privileges

This refactoring significantly improves OSCAR's security posture while simplifying the codebase and maintaining all existing functionality for authorized users.