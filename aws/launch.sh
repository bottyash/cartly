#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Cartly — AWS EC2 Launch Script
#
# Creates a t3.medium instance in ap-south-1 (Mumbai) with:
#   - Ubuntu 22.04 LTS
#   - Security groups for ports 22, 3000, 8000
#   - Elastic IP
#   - The ec2-userdata.sh bootstrap script
#
# Prerequisites:
#   - AWS CLI installed and configured (aws configure)
#   - A key pair created in ap-south-1
#
# Usage:
#   export KEY_NAME=cartly-key   # your EC2 key pair name
#   bash aws/launch.sh
# ══════════════════════════════════════════════════════════════════

set -e

REGION="${AWS_REGION:-ap-south-1}"
KEY_NAME="${KEY_NAME:-cartly-key}"
INSTANCE_TYPE="t3.medium"
PROJECT_TAG="cartly-poc"

# Ubuntu 22.04 LTS AMI for ap-south-1 (update if needed)
AMI_ID="ami-0f58b397bc5c1f2e8"

echo ""
echo "═══════════════════════════════════════════"
echo "  Cartly — Launching EC2 Instance"
echo "  Region: $REGION | Type: $INSTANCE_TYPE"
echo "═══════════════════════════════════════════"
echo ""

# ── 1. Create security group ──────────────────────────────────────
echo "→ Creating security group..."
SG_ID=$(aws ec2 create-security-group \
  --group-name cartly-sg \
  --description "Cartly POC security group" \
  --region "$REGION" \
  --query 'GroupId' \
  --output text 2>/dev/null || \
  aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=cartly-sg" \
    --region "$REGION" \
    --query 'SecurityGroups[0].GroupId' \
    --output text)

echo "  Security Group: $SG_ID"

# Open ports: 22 (SSH), 3000 (Dashboard), 8000 (API)
for PORT in 22 3000 8000; do
  aws ec2 authorize-security-group-ingress \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port "$PORT" \
    --cidr 0.0.0.0/0 \
    --region "$REGION" 2>/dev/null || true
  echo "  Opened port $PORT"
done

# ── 2. Launch instance ────────────────────────────────────────────
echo ""
echo "→ Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --user-data file://aws/ec2-userdata.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$PROJECT_TAG},{Key=Project,Value=cartly}]" \
  --region "$REGION" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "  Instance ID: $INSTANCE_ID"

# ── 3. Wait for running state ─────────────────────────────────────
echo ""
echo "→ Waiting for instance to start (this takes ~60s)..."
aws ec2 wait instance-running \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION"

# ── 4. Allocate Elastic IP ────────────────────────────────────────
echo "→ Allocating Elastic IP..."
ALLOC_ID=$(aws ec2 allocate-address \
  --domain vpc \
  --region "$REGION" \
  --query 'AllocationId' \
  --output text)

PUBLIC_IP=$(aws ec2 associate-address \
  --instance-id "$INSTANCE_ID" \
  --allocation-id "$ALLOC_ID" \
  --region "$REGION" \
  --query 'PublicIp' \
  --output text 2>/dev/null || \
  aws ec2 describe-addresses \
    --allocation-ids "$ALLOC_ID" \
    --region "$REGION" \
    --query 'Addresses[0].PublicIp' \
    --output text)

echo "  Elastic IP: $PUBLIC_IP"

# ── 5. Output ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Instance launched!"
echo ""
echo "  Instance ID : $INSTANCE_ID"
echo "  Public IP   : $PUBLIC_IP"
echo ""
echo "  Wait ~3-4 minutes for bootstrap to complete, then:"
echo ""
echo "  Dashboard : http://$PUBLIC_IP:3000"
echo "  API docs  : http://$PUBLIC_IP:8000/docs"
echo "  Admin     : http://$PUBLIC_IP:3000/admin.html"
echo ""
echo "  SSH       : ssh -i ~/.ssh/$KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo ""
echo "  ⚠️  Edit .env on the instance to add your OpenRouter key:"
echo "  ssh -i ~/.ssh/$KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo "  nano ~/cartly/.env"
echo "  docker compose -f ~/cartly/docker-compose.yml restart api"
echo "═══════════════════════════════════════════"
echo ""

# Save IP to file for CI/CD use
echo "$PUBLIC_IP" > aws/.ec2-ip
