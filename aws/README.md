# Cartly — AWS Deployment Guide

## Architecture

```
                  Internet
                     │
          ┌──────────┴──────────┐
          │  AWS EC2 t3.medium  │
          │  (ap-south-1)       │
          │                     │
          │  :3000  Dashboard   │ ← nginx
          │  :8000  API         │ ← FastAPI + uvicorn
          │  :5432  PostgreSQL  │ ← internal only
          └─────────────────────┘
```

## Prerequisites

- AWS CLI installed and configured (`aws configure`)
- AWS account with EC2 permissions
- An EC2 key pair created in `ap-south-1`
- OpenRouter API key from https://openrouter.ai

## Quick Deploy (First Time)

```bash
# 1. Set your key pair name
export KEY_NAME=cartly-key   # your EC2 key pair name

# 2. Launch the EC2 instance (~2 minutes)
bash aws/launch.sh

# 3. SSH in and edit the .env to add your OpenRouter key
ssh -i ~/.ssh/cartly-key.pem ubuntu@<public-ip>
nano ~/cartly/.env
# → Set OPENROUTER_API_KEY=sk-or-v1-...
# → Set OPENROUTER_SITE_URL=http://<public-ip>:3000

# 4. Restart the API container to pick up the key
docker compose -f ~/cartly/docker-compose.yml restart api

# 5. Wait ~1 min, then open:
open http://<public-ip>:3000
```

## Access URLs (after deploy)

| Service | URL |
|---------|-----|
| Landing page | `http://<ip>:3000` |
| Customer portal | `http://<ip>:3000/user.html` |
| Admin dashboard | `http://<ip>:3000/admin.html` |
| API docs (Swagger) | `http://<ip>:8000/docs` |
| API health | `http://<ip>:8000/health` |

**Admin token:** `cartly-admin-2026` (set via `ADMIN_TOKEN` in `.env`)

## Re-deploy (after code changes)

```bash
# From your local machine:
export EC2_HOST=<public-ip>
export KEY_PATH=~/.ssh/cartly-key.pem
bash aws/deploy.sh
```

## Manual commands on EC2

```bash
ssh -i ~/.ssh/cartly-key.pem ubuntu@<ip>
cd ~/cartly

# View logs
docker compose logs -f api

# Restart all
docker compose restart

# Hard rebuild
docker compose down && docker compose up -d --build

# Check running containers
docker ps

# View observability logs
ls observability/logs/
cat observability/logs/TKT-XXXXXXXX.json
```

## Security Group Ports

| Port | Service | Access |
|------|---------|--------|
| 22 | SSH | Your IP only (recommended) |
| 3000 | Dashboard | Public |
| 8000 | API | Public |
| 5432 | PostgreSQL | Internal only (not exposed) |

## Instance Details

| Setting | Value |
|---------|-------|
| Region | ap-south-1 (Mumbai) |
| Instance type | t3.medium (2 vCPU, 4 GB RAM) |
| OS | Ubuntu 22.04 LTS |
| Storage | 20 GB gp3 |

## Cost Estimate (ap-south-1)

| Resource | Monthly Cost |
|----------|-------------|
| t3.medium | ~$30/month |
| Elastic IP | $0 (when attached) |
| Storage 20 GB | ~$2/month |
| **Total** | **~$32/month** |

> For a POC/submission, you can stop the instance when not presenting — you only pay for running hours.

## Stopping to save costs

```bash
# Stop (keeps data, stops billing for compute)
aws ec2 stop-instances --instance-ids <instance-id> --region ap-south-1

# Start again
aws ec2 start-instances --instance-ids <instance-id> --region ap-south-1
```
