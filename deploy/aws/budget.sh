#!/bin/sh
# Free: emails you when the month's AWS spend passes 80% of the limit, and when the forecast passes 100%.
# Usage: deploy/aws/budget.sh you@example.com [limit-in-USD, default 20]
set -eu
EMAIL=$1
LIMIT=${2:-20}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws budgets create-budget --account-id "$ACCOUNT" \
  --budget "{\"BudgetName\":\"diocle-monthly\",\"BudgetLimit\":{\"Amount\":\"$LIMIT\",\"Unit\":\"USD\"},\"TimeUnit\":\"MONTHLY\",\"BudgetType\":\"COST\"}" \
  --notifications-with-subscribers \
  "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":80},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]},
    {\"Notification\":{\"NotificationType\":\"FORECASTED\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":100},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$EMAIL\"}]}]"
echo "Budget diocle-monthly: alerts at 80% of USD $LIMIT and on a forecast above it, sent to $EMAIL"
