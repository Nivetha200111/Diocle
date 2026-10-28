#!/bin/sh
# Creates the one Lightsail server that hosts Diocle. COSTS MONEY: about USD 12/month for small_3_0 (2 GB RAM,
# 2 vCPU, 60 GB disk; check https://aws.amazon.com/lightsail/pricing/). The static IP is free while attached.
# Usage: deploy/aws/create-server.sh   (needs the AWS CLI logged in: aws configure)
set -eu
REGION=${REGION:-ap-south-1}
ZONE=${ZONE:-${REGION}a}
NAME=${NAME:-diocle}
BUNDLE=${BUNDLE:-small_3_0}

aws lightsail create-instances --region "$REGION" --instance-names "$NAME" --availability-zone "$ZONE" \
  --blueprint-id ubuntu_24_04 --bundle-id "$BUNDLE" \
  --user-data file://"$(dirname "$0")"/bootstrap.sh \
  --tags key=project,value=diocle

aws lightsail allocate-static-ip --region "$REGION" --static-ip-name "$NAME-ip"
until aws lightsail get-instance-state --region "$REGION" --instance-name "$NAME" --query state.name --output text | grep -q running; do sleep 5; done
aws lightsail attach-static-ip --region "$REGION" --static-ip-name "$NAME-ip" --instance-name "$NAME"

# Only web traffic and SSH; the API is never exposed directly.
aws lightsail put-instance-public-ports --region "$REGION" --instance-name "$NAME" --port-infos \
  fromPort=22,toPort=22,protocol=tcp fromPort=80,toPort=80,protocol=tcp fromPort=443,toPort=443,protocol=tcp

echo "Static IP: $(aws lightsail get-static-ip --region "$REGION" --static-ip-name "$NAME-ip" --query staticIp.ipAddress --output text)"
echo "Point your domain's A record at it, then follow docs/DEPLOY.md step 4."
