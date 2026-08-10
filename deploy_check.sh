#!/bin/bash
# Auto-deploy + check script for NEXORA bot
cd /data/workspace/nexora-bot

echo "=== 1. Pushing to GitHub ==="
git add -A
git commit -m "fix: remove stray _check.py" 2>&1 | tail -1
git push origin main 2>&1 | tail -1

echo "=== 2. Waiting for deploy ==="
sleep 90

echo "=== 3. Checking deploy ==="
# Use Railway CLI if logged in, fallback to nothing
railway whoami 2>&1 | head -1
railway status 2>&1 | head -5

echo "=== 4. Done ==="