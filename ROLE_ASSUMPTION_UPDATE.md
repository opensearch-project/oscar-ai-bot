# OSCAR Metrics Role Assumption Update

## Overview

Updated the OSCAR metrics Lambda functions to properly assume the `oscar-metrics-vpc-lambda-role` before making OpenSearch connections. This ensures proper VPC connectivity and permissions for cross-account OpenSearch access.

## Changes Made

### 1. New Role Manager (`metrics/role_manager.py`)
- Handles STS assume role operations
- Manages temporary credentials for OpenSearch access
- Provides error handling and credential caching

### 2. Updated OpenSearch Client (`metrics/opensearch_client.py`)
- Now uses assumed role credentials instead of Lambda execution role
- Improved error handling for role assumption failures
- Better logging for debugging connectivity issues

### 3. Updated Configuration (`metrics/config.py`)
- Added `metrics_role_arn` configuration field
- Default value: `arn:aws:iam::395380602281:role/oscar-metrics-vpc-lambda-role`
- Can be overridden with `METRICS_ROLE_ARN` environment variable

### 4. Updated Lambda Handler (`metrics/lambda_function.py`)
- Enhanced error handling for role assumption failures
- Automatic fallback to mock mode if role assumption fails
- Better logging for troubleshooting

### 5. Updated Deployment Script (`deploy_vpc_lambdas.sh`)
- Added `METRICS_ROLE_ARN` environment variable to Lambda configuration
- Added STS AssumeRole permissions to Lambda execution role
- Enhanced IAM policy for cross-account role assumption

## Environment Variables

Add to your `.env` file (optional, uses default if not set):

```bash
# Role assumption configuration
METRICS_ROLE_ARN=arn:aws:iam::395380602281:role/oscar-metrics-vpc-lambda-role
```

## Deployment Steps

1. **Test Role Assumption (Optional)**:
   ```bash
   python test_role_assumption.py
   ```

2. **Deploy Updated Lambda Functions**:
   ```bash
   ./deploy_vpc_lambdas.sh
   ```

3. **Verify Deployment**:
   ```bash
   # Test each function
   aws lambda invoke --function-name oscar-test-metrics-agent \
     --payload '{"function": "test_connection", "parameters": []}' \
     --cli-binary-format raw-in-base64-out result.json
   
   # Check the result
   cat result.json
   ```

## How It Works

1. **Lambda Execution**: Lambda function starts with its execution role
2. **Role Assumption**: `RoleManager` assumes the `oscar-metrics-vpc-lambda-role`
3. **Credential Usage**: OpenSearch client uses assumed role credentials
4. **VPC Access**: Assumed role has proper VPC and OpenSearch permissions
5. **Fallback**: If role assumption fails, function falls back to mock mode

## Permissions Required

### Lambda Execution Role Needs:
- `sts:AssumeRole` permission for `oscar-metrics-vpc-lambda-role`
- Basic Lambda execution permissions
- VPC access permissions

### Target Role (`oscar-metrics-vpc-lambda-role`) Needs:
- OpenSearch access permissions
- VPC connectivity permissions
- Trust relationship allowing Lambda execution role to assume it

## Troubleshooting

### Role Assumption Fails
- Check if `oscar-metrics-vpc-lambda-role` exists
- Verify trust relationship allows Lambda execution role
- Check CloudWatch logs for detailed error messages

### OpenSearch Connection Fails
- Verify VPC endpoint configuration
- Check security group rules
- Ensure OpenSearch domain allows access from assumed role

### Mock Mode Activation
- Function automatically falls back to mock mode if role assumption fails
- Check logs for "falling back to mock mode" messages
- Verify role ARN configuration

## Testing

The functions now include enhanced error handling:
- Role assumption failures are logged and handled gracefully
- Automatic fallback to mock mode for testing
- Detailed logging for troubleshooting connectivity issues

## Files Modified

- `metrics/role_manager.py` (new)
- `metrics/opensearch_client.py`
- `metrics/config.py`
- `metrics/lambda_function.py`
- `deploy_vpc_lambdas.sh`
- `test_role_assumption.py` (new)

## Next Steps

After deployment:
1. Monitor CloudWatch logs for role assumption success/failure
2. Test end-to-end functionality with actual OpenSearch queries
3. Verify VPC connectivity and security group configurations
4. Update Bedrock agent configurations if needed