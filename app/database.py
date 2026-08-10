"""Database layer for NEXORA bot.
Includes customer data, orders, services, support tickets, and settings.
Backup-safe: all schema mutations use ALTER TABLE IF NOT EXISTS or guards.
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

_lock = threading.RLock()


def _parse_db_path() -> str:
    from app import config
    return config.DB_PATH


def get_conn():
    path = _parse_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
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
                status TEXT DEFAULT 'pending',
                -- pending | paid | delivered | active | deactivated | refunded | cancelled | failed
                created_at TEXT,
                payment_charge_id TEXT,
                activated_at TEXT,
                config_delivered_at TEXT,
                delivery_note TEXT           -- admin notes / manual config label
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
                status TEXT DEFAULT 'active',
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
            """
        )


def _ensure_column(table: str, column: str, col_type: str, default=None):
    """Add a column only if it doesn't exist (SQLite-safe)."""
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            default_clause = f" DEFAULT {default}" if default is not None else ""
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")


def migrate_schema():
    """Ensure newer columns exist on databases created before the latest code."""
    _ensure_column("orders", "config_delivered_at", "TEXT")
    _ensure_column("orders", "delivery_note", "TEXT")


# ─── Users ─────────────────────────────────────────────────────────────────────

def get_user(telegram_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


def create_user(telegram_id, username, first_name):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name, created_at) VALUES (?,?,?,?)",
            (telegram_id, username, first_name, datetime.utcnow().isoformat()),
        )
        conn.execute(
            "UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
            (username, first_name, telegram_id),
        )
        return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


def mark_test_used(telegram_id, test_bytes):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET test_used=1, test_bytes=? WHERE telegram_id=?",
            (test_bytes, telegram_id),
        )


def can_use_test(telegram_id):
    u = get_user(telegram_id)
    return u is None or u["test_used"] == 0


# ─── Orders ────────────────────────────────────────────────────────────────────

def create_order(telegram_id, plan_gb, price_toman, price_stars):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (telegram_id, plan_gb, price_toman, price_stars, status, created_at) "
            "VALUES (?,?,?,?,'pending',?)",
            (telegram_id, plan_gb, price_toman, price_stars, datetime.utcnow().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def get_order(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()


def set_order_status(order_id, status, payment_charge_id=None):
    with get_conn() as conn:
        if payment_charge_id:
            conn.execute(
                "UPDATE orders SET status=?, payment_charge_id=?, activated_at=? WHERE id=?",
                (status, payment_charge_id, datetime.utcnow().isoformat(timespec="seconds"), order_id),
            )
        else:
            conn.execute(
                "UPDATE orders SET status=? WHERE id=?",
                (status, order_id),
            )
        conn.commit()


def set_config_delivered(order_id, note=""):
    """Mark an order as having its config delivered (with an optional note/label)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status='delivered', config_delivered_at=?, delivery_note=? WHERE id=?",
            (datetime.utcnow().isoformat(timespec="seconds"), note, order_id),
        )
        conn.commit()


# ─── Services ───────────────────────────────────────────────────────────────────

def create_service(order_id, telegram_id, uuid, label, volume_gb, subscription_url, vless_link, expires_at):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO services (order_id, telegram_id, uuid, label, volume_gb, expires_at, subscription_url, vless_link, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (order_id, telegram_id, uuid, label, volume_gb, expires_at, subscription_url, vless_link, datetime.utcnow().isoformat(timespec="seconds")),
        )
        res_id = cur.lastrowid
        _check_volume_threshold()
        return res_id


def _check_volume_threshold():
    """Notify admin when total sold volume hits the threshold (once)."""
    try:
        total_sold = total_sold_gb_all()
        threshold = config.VOLUME_ALERT_THRESHOLD_GB
        already_alerted = get_setting("alert_volume_sent")
        if total_sold >= threshold and not already_alerted:
            set_setting("alert_volume_sent", "1")
            import asyncio
            from app.instances import bot

            async def notify_admin():
                try:
                    await bot.send_message(
                        config.ADMIN_ID,
                        f"🎉 **تبریک! مجموع فروش به {threshold:g} گیگابایت رسید!** 🚀\n\n"
                        f"مجموع فروش کل سیستم: **{total_sold:.1f} GB**",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(notify_admin())
            except Exception:
                pass
    except Exception:
        pass


def get_service_for_user(telegram_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM services WHERE telegram_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()


def deactivate_service(uuid):
    with get_conn() as conn:
        conn.execute("UPDATE services SET status='deactivated' WHERE uuid=?", (uuid,))


def total_sold_gb():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(volume_gb),0) AS total FROM services WHERE status!='deactivated'"
        ).fetchone()
        return row["total"]


def total_sold_gb_all():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(volume_gb),0) AS total FROM services"
        ).fetchone()
        return row["total"]


# ─── Deferred payments (legacy / unused) ───────────────────────────────────────

def add_deferred_payment(telegram_id, order_id, stars_amount):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO payments_deferred (telegram_id, order_id, stars_amount, created_at) VALUES (?,?,?,?)",
            (telegram_id, order_id, stars_amount, datetime.utcnow().isoformat(timespec="seconds")),
        )


def clear_deferred_payment(order_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM payments_deferred WHERE order_id=?", (order_id,))


# ─── Tickets ───────────────────────────────────────────────────────────────────

def create_ticket(telegram_id, subject, message):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (telegram_id, subject, message, created_at) VALUES (?,?,?,?)",
            (telegram_id, subject, message, datetime.utcnow().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


# ─── Settings (key/value) ──────────────────────────────────────────────────────

def get_setting(key):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, value),
        )