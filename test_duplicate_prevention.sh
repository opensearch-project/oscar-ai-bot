#!/bin/bash
# Test duplicate response prevention

echo "🧪 Testing duplicate response prevention..."

# Simulate the same event sent multiple times (as Slack would do on retry)
EVENT_PAYLOAD='{
  "token": "verification_token",
  "team_id": "T123456",
  "api_app_id": "A123456",
  "event": {
    "type": "app_mention",
    "user": "U123456",
    "text": "<@UBOT123456> hello test",
    "ts": "1234567890.123456",
    "channel": "C123456",
    "event_ts": "1234567890.123456"
  },
  "type": "event_callback",
  "event_id": "Ev123456",
  "event_time": 1234567890
}'

echo "📤 Sending first request..."
curl -s -X POST https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test_signature_1" \
  -d "$EVENT_PAYLOAD" &

echo "📤 Sending duplicate request (simulating Slack retry)..."
curl -s -X POST https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test_signature_2" \
  -d "$EVENT_PAYLOAD" &

echo "📤 Sending third request (simulating another retry)..."
curl -s -X POST https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: $(date +%s)" \
  -H "X-Slack-Signature: v0=test_signature_3" \
  -d "$EVENT_PAYLOAD" &

wait

echo -e "\n✅ All requests sent. Check Lambda logs to verify immediate acknowledgment:"
echo "aws logs tail /aws/lambda/oscar-supervisor-agent --follow --region us-east-1"