import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

_lock = threading.RLock()

def get_conn():
    conn = sqlite3.connect("nexora.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT,
            test_used INTEGER DEFAULT 0,
            test_bytes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            plan_gb INTEGER,
            price_toman INTEGER,
            price_stars INTEGER,
            status TEXT DEFAULT 'pending', -- pending | payment_received | active | deactivated | refunded
            created_at TEXT,
            payment_charge_id TEXT,
            activated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            telegram_id INTEGER,
            uuid TEXT UNIQUE,
            label TEXT,
            volume_gb REAL,
            used_bytes INTEGER DEFAULT 0,
            expires_at TEXT,
            subscription_url TEXT,
            vless_link TEXT,
            status TEXT DEFAULT 'active', -- active | deactivated | expired
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS payments_deferred (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            order_id INTEGER,
            stars_amount INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

def get_user(telegram_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()

def create_user(telegram_id, username, first_name):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name, created_at) VALUES (?,?,?,?)",
                     (telegram_id, username, first_name, datetime.utcnow().isoformat()))
        conn.execute("UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                     (username, first_name, telegram_id))
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()

def mark_test_used(telegram_id, test_bytes):
    with get_conn() as conn:
        conn.execute("UPDATE users SET test_used=1, test_bytes=? WHERE telegram_id=?", (test_bytes, telegram_id))

def can_use_test(telegram_id):
    return get_user(telegram_id) is None or get_user(telegram_id)["test_used"] == 0

def create_order(telegram_id, plan_gb, price_toman, price_stars):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (telegram_id, plan_gb, price_toman, price_stars, status, created_at) VALUES (?,?,?,?,'pending',?)",
            (telegram_id, plan_gb, price_toman, price_stars, datetime.utcnow().isoformat()))
        return cur.lastrowid

def get_order(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()

def set_order_status(order_id, status, payment_charge_id=None):
    with get_conn() as conn:
        if payment_charge_id:
            conn.execute("UPDATE orders SET status=?, payment_charge_id=?, activated_at=? WHERE id=?",
                         (status, payment_charge_id, datetime.utcnow().isoformat(), order_id))
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

def create_service(order_id, telegram_id, uuid, label, volume_gb, subscription_url, vless_link, expires_at):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO services (order_id, telegram_id, uuid, label, volume_gb, expires_at, subscription_url, vless_link, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (order_id, telegram_id, uuid, label, volume_gb, expires_at, subscription_url, vless_link, datetime.utcnow().isoformat()))
        res_id = cur.lastrowid
        
        # Check total 100GB threshold
        try:
            total_sold = total_sold_gb_all()
            already_alerted = get_setting("alert_100gb_sent")
            if total_sold >= 100.0 and not already_alerted:
                set_setting("alert_100gb_sent", "1")
                # Trigger notification asynchronously if bot loop is available
                import asyncio
                from app import config
                async def notify_admin():
                    try:
                        from app.instances import bot
                        await bot.send_message(
                            config.ADMIN_ID,
                            f"🎉 **تبریک! مجموع فروش به ۱۰۰ گیگابایت رسید!** 🚀\n\n"
                            f"مجموع فروش کل سیستم: **{total_sold:.1f} GB**",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        pass
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(notify_admin())
                except Exception:
                    pass
        except Exception:
            pass

        return res_id

def get_service_for_user(telegram_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM services WHERE telegram_id=? AND status='active' ORDER BY id DESC LIMIT 1", (telegram_id,)).fetchone()

def deactivate_service(uuid):
    with get_conn() as conn:
        conn.execute("UPDATE services SET status='deactivated' WHERE uuid=?", (uuid,))

def create_ticket(telegram_id, subject, message):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (telegram_id, subject, message, created_at) VALUES (?,?,?,?)",
            (telegram_id, subject, message, datetime.utcnow().isoformat()))
        return cur.lastrowid

def total_sold_gb():
    with get_conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(volume_gb),0) AS total FROM services WHERE status!='deactivated'").fetchone()
        return row["total"]

def total_sold_gb_all():
    with get_conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(volume_gb),0) AS total FROM services").fetchone()
        return row["total"]

def add_deferred_payment(telegram_id, order_id, stars_amount):
    with get_conn() as conn:
        conn.execute("INSERT INTO payments_deferred (telegram_id, order_id, stars_amount, created_at) VALUES (?,?,?,?)",
                     (telegram_id, order_id, stars_amount, datetime.utcnow().isoformat()))

def clear_deferred_payment(order_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM payments_deferred WHERE order_id=?", (order_id,))

def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))