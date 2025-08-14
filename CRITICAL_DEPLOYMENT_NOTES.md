# 🚨 CRITICAL DEPLOYMENT NOTES - READ BEFORE DEPLOYING

## ⚠️ NEVER DEPLOY WITHOUT THESE FIXES

This file contains **CRITICAL INFORMATION** that must be followed to prevent OSCAR from breaking. These fixes were discovered after extensive debugging and **MUST NOT BE LOST**.

## 🔥 Quick Emergency Fix

If OSCAR is broken and you need it working immediately:

```bash
./fix_oscar_deployment.sh
```

This script applies all critical fixes automatically.

## 📋 Critical Checklist Before Any Deployment

- [ ] Environment variables use `oscar-agent-context` and `oscar-agent-sessions` table names
- [ ] IAM role `oscar-supervisor-lambda-role` has permissions for these table names
- [ ] `storage.py` contains `get_context_for_query` method
- [ ] `slack_handler.py` uses `stored_context` and `formatted_context` variables (not `context`)
- [ ] Deployment package is created with Python zip method (not bash `cd && zip`)
- [ ] All dependencies are installed with `--upgrade` flag

## 🚨 Known Breaking Issues

### 1. **Variable Name Collision**
**Symptom**: `AttributeError: 'DynamoDBStorage' object has no attribute 'get_context_for_query'`
**Cause**: Variable `context` is reused in `slack_handler.py`
**Fix**: Use `stored_context` and `formatted_context` variables

### 2. **Wrong Table Names**
**Symptom**: `AccessDeniedException` for DynamoDB
**Cause**: IAM policy points to old table names
**Fix**: Update policy to use `oscar-agent-context` and `oscar-agent-sessions`

### 3. **Import Module Error**
**Symptom**: `No module named 'lambda_function'`
**Cause**: Zip file has wrong structure (nested paths)
**Fix**: Use Python to create zip file, not bash `cd && zip`

### 4. **Missing Dependencies**
**Symptom**: Bot does nothing, no reactions
**Cause**: Dependencies not properly installed
**Fix**: Use `pip install --upgrade` and verify installation

## 📁 Files That Must Be Correct

1. **oscar-agent/slack_handler.py** - Lines 518-522 must use correct variable names
2. **oscar-agent/storage.py** - Must have `get_context_for_query` method
3. **oscar-agent/config.py** - Default table names must be `oscar-agent-*`
4. **.env** - Must have correct `CONTEXT_TABLE_NAME` and `SESSIONS_TABLE_NAME`
5. **update_slack_agent.sh** - Must use Python zip creation method

## 🔧 Emergency Commands

```bash
# Check if OSCAR is working
python debug_context_preservation.py

# Check Lambda logs for errors
aws logs describe-log-streams --log-group-name "/aws/lambda/oscar-supervisor-agent" --order-by LastEventTime --descending --max-items 1 --region us-east-1

# Fix IAM permissions
aws iam put-role-policy --role-name oscar-supervisor-lambda-role --policy-name DynamoDBAccess --policy-document file://dynamodb-policy.json

# Manual deployment (last resort)
./fix_oscar_deployment.sh
```

## 📞 Troubleshooting Decision Tree

1. **OSCAR not responding at all**
   → Check CloudWatch logs for import errors
   → Run `./fix_oscar_deployment.sh`

2. **OSCAR responds with red X immediately**
   → Check for `AttributeError` in logs
   → Verify `storage.py` has `get_context_for_query` method
   → Redeploy with correct code

3. **OSCAR responds but no context preservation**
   → Check DynamoDB permissions
   → Verify table names in environment variables
   → Run `python debug_context_preservation.py`

## 💾 Backup of Working Configuration

**Working .env settings:**
```
CONTEXT_TABLE_NAME=oscar-agent-context
SESSIONS_TABLE_NAME=oscar-agent-sessions
```

**Working IAM policy:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem", 
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan"
            ],
            "Resource": [
                "arn:aws:dynamodb:us-east-1:*:table/oscar-agent-sessions",
                "arn:aws:dynamodb:us-east-1:*:table/oscar-agent-context"
            ]
        }
    ]
}
```

## 🎯 Success Verification

After deployment, these should work:
- `@oscar hello` → Gets proper response
- Thread conversation → Context preserved
- No errors in CloudWatch logs
- `python debug_context_preservation.py` → All tests pass

---

**🚨 REMEMBER: If you ignore these notes, OSCAR will break and you'll spend hours debugging the same issues again!**