#!/bin/bash
# Test bot mention functionality

echo "🧪 Testing bot mention..."

curl -X POST https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test_signature" \
  -d '{
    "token": "verification_token",
    "team_id": "T123456",
    "api_app_id": "A123456",
    "event": {
      "type": "app_mention",
      "user": "U123456",
      "text": "<@UBOT123456> hello",
      "ts": "1234567890.123456",
      "channel": "C123456",
      "event_ts": "1234567890.123456"
    },
    "type": "event_callback",
    "event_id": "Ev123456",
    "event_time": 1234567890
  }'

echo -e "\n✅ Test completed"