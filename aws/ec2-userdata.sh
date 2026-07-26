#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Cartly — EC2 User Data Bootstrap Script
# Runs on first boot of a fresh Ubuntu 22.04 LTS instance.
# Installs Docker, clones repo, and starts docker-compose.
#
# BEFORE USING: paste your OPENROUTER_API_KEY below.
# ══════════════════════════════════════════════════════════════════

set -e
exec > /var/log/cartly-bootstrap.log 2>&1

echo "=== Cartly Bootstrap Starting: $(date) ==="

# ── 1. System update ──────────────────────────────────────────────
apt-get update -y
apt-get install -y \
  docker.io \
  docker-compose \
  git \
  curl \
  htop \
  unzip

# ── 2. Start Docker ───────────────────────────────────────────────
systemctl start docker
systemctl enable docker
usermod -aG docker ubuntu

# ── 3. Clone the repository ───────────────────────────────────────
cd /home/ubuntu
git clone https://github.com/bottyash/cartly.git
cd cartly

# ── 3a. Get this instance's public IP via IMDSv2 ─────────────────
EC2_PUBLIC_IP=$(curl -sf \
  -H "X-aws-ec2-metadata-token: $(curl -sf -X PUT \
    'http://169.254.169.254/latest/api/token' \
    -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600')" \
  http://169.254.169.254/latest/meta-data/public-ipv4 || echo '0.0.0.0')

# ── 4. Create .env ────────────────────────────────────────────────
# !! FILL IN YOUR VALUES BELOW !!
cat > .env << 'ENVEOF'
# OpenRouter — REQUIRED
OPENROUTER_API_KEY=sk-or-v1-PASTE_YOUR_KEY_HERE
OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_SITE_URL=http://${EC2_PUBLIC_IP}
OPENROUTER_SITE_NAME=Cartly

# PostgreSQL
POSTGRES_DSN=postgresql://cartly:cartly_secret@postgres:5432/cartly
POSTGRES_DB=cartly
POSTGRES_USER=cartly
POSTGRES_PASSWORD=cartly_secret
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Admin
ADMIN_TOKEN=cartly-admin-2026

# API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=production
LOG_LEVEL=info

# Observability
LOG_DIR=/app/observability/logs

# Refund Thresholds
THRESHOLD_AMOUNT=500
FAITHFULNESS_FLOOR=0.70

# CORS
APP_URL=http://${EC2_PUBLIC_IP}
ALLOWED_ORIGINS=http://${EC2_PUBLIC_IP},http://${EC2_PUBLIC_IP}:8000,http://${EC2_PUBLIC_IP}:3000
ENVEOF

# ── 5. Fix ownership ──────────────────────────────────────────────
chown -R ubuntu:ubuntu /home/ubuntu/cartly

# ── 6. Start services ─────────────────────────────────────────────
# Run as ubuntu user (docker group)
sudo -u ubuntu bash -c "
  cd /home/ubuntu/cartly
  docker compose up -d --build
"

echo "=== Bootstrap Complete: $(date) ==="
echo "Dashboard: http://${EC2_PUBLIC_IP}  (port 80)"
echo "Dashboard: http://${EC2_PUBLIC_IP}:3000  (alt port)"
echo "API:       http://${EC2_PUBLIC_IP}:8000/docs"
