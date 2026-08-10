#!/bin/bash
cd /data/workspace/nexora-bot
git rm --cached _status.py 2>/dev/null
rm -f _status.py
git add -A
git commit --amend --no-edit -m "Secure payments: real Telegram Stars invoices; /reply /order /backup commands; daily backup + Railway plan expiry warning"
git push origin main --force
