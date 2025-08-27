# Automatic Secrets Refresh Solution

## Problem Solved
Previously, when secrets were updated in AWS Secrets Manager, Lambda functions would continue using cached values until the container was recycled or code was redeployed. This required manual intervention to see configuration changes.

## Solution
Implemented dynamic properties that fetch fresh secrets on every access:

### How It Works
1. **Dynamic Properties**: Config attributes are now `@property` methods
2. **Fresh Secrets**: Each property access calls `_load_env_from_secrets()`
3. **Immediate Updates**: Latest secrets are loaded from AWS on every config access
4. **No Caching**: No cached values - always fresh from Secrets Manager

### Key Features
- **Zero Manual Intervention**: Secrets updates take effect immediately
- **Real-time**: Every config access gets the absolute latest values
- **Fallback Safe**: Continues with local environment if Secrets Manager fails
- **Simple**: No complex caching logic or version checking needed

### Files Modified
- `jenkins/config.py` - Converted attributes to dynamic properties

### Example
```python
# Every time this is accessed, fresh secrets are loaded
token = config.jenkins_api_token  # Calls AWS Secrets Manager
url = config.jenkins_url         # Calls AWS Secrets Manager again
```

### Usage
No changes required in your code. Every time you access any config property:
1. Fresh secrets are loaded from AWS Secrets Manager
2. Environment variables are updated with latest values
3. The property returns the fresh value

### Benefits
- **Immediate Effect**: Configuration changes take effect on next access
- **Simple**: No complex caching or version checking
- **Reliable**: Always gets the latest values
- **Transparent**: No code changes needed in Lambda handlers