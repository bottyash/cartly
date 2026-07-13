#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Cartly — Deploy latest code to existing EC2 instance
#
# Usage:
#   export EC2_HOST=<public-ip>
#   export KEY_PATH=~/.ssh/cartly-key.pem
#   bash aws/deploy.sh
# ══════════════════════════════════════════════════════════════════

set -e

EC2_HOST="${EC2_HOST:-$(cat aws/.ec2-ip 2>/dev/null || echo '')}"
EC2_USER="${EC2_USER:-ubuntu}"
KEY_PATH="${KEY_PATH:-~/.ssh/cartly-key.pem}"

if [ -z "$EC2_HOST" ]; then
  echo "Error: EC2_HOST is not set. Run aws/launch.sh first or export EC2_HOST=<ip>"
  exit 1
fi

echo ""
echo "→ Deploying to $EC2_USER@$EC2_HOST"

ssh -i "$KEY_PATH" \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=30 \
    "$EC2_USER@$EC2_HOST" << 'REMOTE'
  set -e
  cd ~/cartly
  echo "  Pulling latest code..."
  git pull origin main
  echo "  Rebuilding containers..."
  docker compose up -d --build
  echo "  Running containers:"
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
REMOTE

echo ""
echo "✅ Deployment complete!"
echo "   Dashboard: http://$EC2_HOST:3000"
echo "   API:       http://$EC2_HOST:8000/docs"
