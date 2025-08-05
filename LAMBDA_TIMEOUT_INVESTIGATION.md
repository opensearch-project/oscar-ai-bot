# Lambda Timeout Investigation Report

## Issue Summary

The OSCAR metrics Lambda functions are experiencing infinite timeouts/loops when attempting to connect to the cross-account OpenSearch cluster, despite having proper permissions and role assumption capabilities.

## Background

The Lambda functions need to:
1. Assume the cross-account role `arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole`
2. Use those credentials to connect to OpenSearch cluster in account `979020455945`
3. Query metrics data from the cluster

## Investigation Timeline

### Initial State (WORKING)
- Lambda functions were deployed with basic OpenSearch connectivity
- Functions responded quickly with **403 authorization errors**
- **CRITICAL**: No timeout issues - Lambda returned proper error responses
- Error showed: `User: arn:aws:sts::395380602281:assumed-role/oscar-metrics-lambda-vpc-role/oscar-build-metrics-agent is not authorized to perform: es:ESHttpPost`
- This proves **network connectivity was working** - just permissions issue

### Problem Introduction (REGRESSION)
- **REGRESSION**: After implementing cross-account role assumption, Lambda functions began timing out
- **Before**: Fast 403 errors (network working, permissions issue)
- **After**: Infinite timeouts/loops (network or initialization blocking)
- Functions would not respond to invocations, appearing to loop infinitely
- No CloudWatch logs were generated, indicating failure during initialization
- **KEY INSIGHT**: We broke working network connectivity by changing the authentication method

### Debugging Steps Taken

#### 1. Role Permission Verification
**Action**: Verified Lambda execution role has STS AssumeRole permission
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": "arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole"
        }
    ]
}
```
**Result**: ✅ Permissions confirmed correct

#### 2. Isolated Role Assumption Testing
**Action**: Created minimal test Lambda to isolate role assumption
**Result**: ✅ Role assumption works perfectly in isolation
- Successfully assumes cross-account role
- No timeout issues
- Works both with and without VPC configuration

#### 3. OpenSearch Client Library Investigation
**Action**: Suspected opensearch-py and aws-requests-auth libraries causing blocking
**Attempts**:
- Lazy initialization of OpenSearch client
- Shorter timeouts and fewer retries
- Direct HTTP requests instead of opensearch-py library
**Result**: ❌ All attempts still resulted in timeouts

#### 4. VPC Connectivity Testing
**Action**: Tested if VPC configuration causes issues
**Result**: ✅ VPC configuration works fine for basic operations

## Key Findings

### What Works
1. **Role Assumption**: Cross-account role assumption works perfectly in isolation
2. **VPC Connectivity**: Lambda functions can operate in VPC without issues
3. **Basic Lambda Operations**: Simple Lambda functions respond normally

### What Fails
1. **OpenSearch Client Initialization**: Any attempt to initialize OpenSearch client causes timeout
2. **Library Dependencies**: Both opensearch-py and direct HTTP approaches fail
3. **Metrics Lambda Functions**: All metrics Lambda functions timeout during initialization

## Root Cause Analysis

### Most Likely Cause: Authentication Method Regression
The evidence points to a **blocking issue introduced by the cross-account role assumption implementation**.

**Critical Evidence**:
- **BEFORE**: Lambda returned fast 403 errors (network working, just permissions issue)
- **AFTER**: Lambda times out infinitely (blocking during initialization)
- **REGRESSION**: We broke working network connectivity by changing authentication
- Role assumption works in isolation (different Lambda, simpler code)
- VPC configuration works for basic operations
- Timeout occurs during OpenSearch client initialization with assumed credentials
- No CloudWatch logs generated (failure during cold start)

### Likely Root Causes (In Order of Probability):
1. **OpenSearch Client Library Blocking**: aws-requests-auth or opensearch-py blocking on assumed credentials
2. **Credential Refresh Loop**: Client attempting to refresh expired/invalid assumed credentials
3. **DNS/Network Issue**: Assumed role credentials causing different network path
4. **Library Incompatibility**: opensearch-py not handling assumed role credentials properly

### Possible Network Issues
1. **Security Group Rules**: VPC security groups may not allow HTTPS traffic to OpenSearch endpoint
2. **Route Table Configuration**: Missing routes to OpenSearch VPC endpoint
3. **NAT Gateway Issues**: Lambda in private subnets may lack internet access for STS calls
4. **DNS Resolution**: VPC may not resolve OpenSearch endpoint correctly
5. **Cross-Account VPC Endpoint**: Endpoint may not be configured for cross-account access

## Recommended Solutions

### Immediate Actions (Based on Regression Analysis)
1. **Revert to Working Authentication**:
   - Temporarily revert to original authentication method that gave 403 errors
   - Confirm network connectivity is restored
   - This isolates the issue to authentication implementation

2. **Compare Working vs Broken Code**:
   - Identify exact differences between working (403 error) and broken (timeout) versions
   - Focus on credential handling and OpenSearch client initialization

3. **Test Assumed Credentials Outside OpenSearch Client**:
   - Use assumed credentials for simple AWS API calls (S3, EC2) to verify they work
   - Test if issue is specific to OpenSearch client libraries

4. **Implement Timeout Protection**:
   - Add explicit timeouts to role assumption and client initialization
   - Implement circuit breaker pattern to prevent infinite loops

### Network Troubleshooting Steps
1. **Deploy Network Test Lambda**:
   - Test DNS resolution of OpenSearch endpoint
   - Test HTTPS connectivity to endpoint
   - Test STS connectivity from within VPC

2. **Review VPC Endpoint Configuration**:
   - Verify OpenSearch VPC endpoint allows cross-account access
   - Check endpoint policy allows assumed role access

3. **Security Group Analysis**:
   - Ensure Lambda security group allows outbound HTTPS
   - Verify no conflicting inbound/outbound rules

### Alternative Approaches
1. **Mock Mode Fallback**: Implement automatic fallback to mock mode on timeout
2. **Connection Pooling**: Use persistent connections to reduce initialization overhead
3. **Async Initialization**: Move OpenSearch client initialization to first use rather than Lambda init

## Current Status

### Working Components
- ✅ Cross-account role assumption
- ✅ Lambda execution role permissions
- ✅ VPC Lambda deployment
- ✅ Basic Lambda functionality

### Failing Components
- ❌ OpenSearch client initialization
- ❌ Network connectivity to OpenSearch cluster
- ❌ Metrics data retrieval

### Next Steps for Mentor Discussion
1. **Regression Analysis**: Explain that Lambda worked before (403 errors) but now times out
2. **Authentication Method Review**: Discuss if cross-account role assumption is causing library issues
3. **Alternative Authentication**: Consider if there's a different way to authenticate cross-account
4. **Library Investigation**: Determine if opensearch-py/aws-requests-auth have known issues with assumed roles
5. **Fallback Strategy**: Implement timeout protection and graceful degradation

## Code State

The codebase has been reverted to a clean state with only essential cross-account role assumption functionality:
- Role assumption logic maintained
- OpenSearch client simplified to original form
- Lambda execution role has proper STS permissions
- Configuration points to correct cross-account role

**CRITICAL FINDING**: This is a regression issue. The Lambda previously worked (returned 403 errors quickly) but now times out after implementing cross-account role assumption. This suggests the issue is in the authentication/credential handling code, not infrastructure. The network connectivity was proven to work before our changes.

**RECOMMENDATION**: Focus on the authentication implementation rather than network troubleshooting, as we broke working functionality.