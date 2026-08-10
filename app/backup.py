"""Backup system: copies the DB to a private GitHub repo + sends to admin Telegram chat.
Protects customer data if Railway free trial ends or account is lost.
"""
import asyncio
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime

import aiohttp
from app import config

# GitHub backup repo (private). Configure via env GITHUB_BACKUP_REPO.
# Format: "owner/repo" e.g. "nextro233/nexora-backup"
GITHUB_BACKUP_REPO = os.getenv("GITHUB_BACKUP_REPO", "nextro233/nexora-backup")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DB_PATH = config.DB_PATH


def export_db_to_sql_json() -> dict:
    """Dump all tables to a JSON structure (works even if SQLite file is locked)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tables = [
        "users", "orders", "services", "payments_deferred", "tickets", "settings",
    ]
    data = {}
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            data[t] = [dict(r) for r in rows]
        except Exception as e:
            data[t] = {"error": str(e)}
    conn.close()
    return data


def make_backup_bytes() -> bytes:
    """Produce a .db backup file (SQLite VACUUM INTO)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(f"VACUUM INTO '{tmp}'")
        conn.close()
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


async def upload_to_github(payload: str, filename: str) -> bool:
    """Upload a file to the private backup repo via GitHub Contents API (async)."""
    if not GITHUB_TOKEN:
        return False

    import base64
    content_b64 = base64.b64encode(payload.encode()).decode()

    url = f"https://api.github.com/repos/{GITHUB_BACKUP_REPO}/contents/backups/{filename}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "nexora-backup",
    }

    async with aiohttp.ClientSession() as session:
        sha = None
        # Check if file exists (to get sha for update)
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sha = data.get("sha")
        except Exception:
            pass  # 404 = new file

        body = {"message": f"backup {filename}", "content": content_b64}
        if sha:
            body["sha"] = sha

        try:
            async with session.put(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            print(f"GitHub upload failed: {e}")
            return False


async def send_backup_to_admin() -> str:
    """Send DB + JSON snapshot to admin chat. Returns a summary message."""
    from app.instances import bot

    # 1. JSON snapshot (human-readable)
    snapshot = export_db_to_sql_json()
    summary = _summarize(snapshot)

    # 2. DB binary backup
    db_bytes = make_backup_bytes()

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Try GitHub upload (if configured)
    gh_ok = False
    if GITHUB_TOKEN:
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
        gh_ok = await upload_to_github(payload, f"snapshot_{ts}.json")

    # Send to admin
    ok_sent = False
    try:
        await bot.send_document(
            config.ADMIN_ID,
            io.BytesIO(db_bytes),
            filename=f"nexora_backup_{ts}.db",
            caption=f"📦 **بکاپ کامل دیتابیس NEXORA**\n{summary}\n\n⏰ {ts} UTC",
            parse_mode="Markdown",
        )
        ok_sent = True
    except Exception as e:
        print(f"Admin backup send failed: {e}")

    gh_note = "✅ آپلود به گیت‌هاب شد" if gh_ok else ("⚠️ گیت‌هاب ست نشده" if not GITHUB_TOKEN else "❌ آپلود گیت‌هاب ناموفق")
    return f"بکاپ: DB به تلگرام {'✅' if ok_sent else '❌'} | {gh_note}"


def _summarize(snapshot: dict) -> str:
    users = len(snapshot.get("users", []))
    orders = len(snapshot.get("orders", []))
    services = len(snapshot.get("services", []))
    paid_orders = sum(1 for o in snapshot.get("orders", []) if o.get("status") in ("paid", "active", "delivered"))
    total_gb = sum(s.get("volume_gb", 0) for s in snapshot.get("services", []))
    return (
        f"👥 کاربران: {users}\n"
        f"🧾 سفارش‌ها: {orders} (پرداخت‌شده: {paid_orders})\n"
        f"📦 سرویس‌ها: {services} — {total_gb:.1f} GB"
    )


def get_deploy_start_date() -> datetime:
    """Approx deployment start = earliest order/user created_at, else now."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT MIN(created_at) as m FROM users").fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
    except Exception:
        pass
    finally:
        conn.close()
    return datetime.utcnow()