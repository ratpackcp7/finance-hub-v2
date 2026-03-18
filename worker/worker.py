"""
Finance Hub v2 — Background Worker
Runs a daily SimpleFIN sync + retention purge via APScheduler.
"""

import logging
import os
import time
from datetime import date
from pathlib import Path

import psycopg2
import psycopg2.pool
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from shared.syncer import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))


# ─────────────────────────────────────────────
# DB pool
# ─────────────────────────────────────────────

def read_secret(name: str) -> str:
    p = Path(f"/run/secrets/{name}")
    if p.exists():
        return p.read_text().strip()
    val = os.environ.get(name.upper())
    if val:
        return val
    raise RuntimeError(f"Secret '{name}' not found")


_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=3,
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=read_secret("db_password"),
        )
    return _pool


# ─────────────────────────────────────────────
# Scheduled jobs
# ─────────────────────────────────────────────

def take_balance_snapshot(conn):
    """Record current account balances. Idempotent per date."""
    cur = conn.cursor()
    today = date.today()
    cur.execute("""
        INSERT INTO balance_snapshots (snapshot_date, account_id, account_name, account_type, balance)
        SELECT %s, id, name, COALESCE(account_type, 'checking'), balance
        FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL
        ON CONFLICT (snapshot_date, account_id) DO UPDATE SET
            balance = EXCLUDED.balance,
            account_name = EXCLUDED.account_name,
            account_type = EXCLUDED.account_type
    """, (today,))
    count = cur.rowcount
    conn.commit()
    logger.info("Balance snapshot: %d accounts for %s", count, today)
    return count


def purge_old_payloads(conn):
    """Null out raw_payload on old import batches + per-txn raw JSON.
    Keeps batch metadata (counts, status, timestamps) forever."""
    cur = conn.cursor()
    cur.execute("SELECT purge_old_payloads(%s)", (RETENTION_DAYS,))
    batch_purged = cur.fetchone()[0]
    cur.execute("SELECT purge_old_txn_raw(%s)", (RETENTION_DAYS,))
    txn_purged = cur.fetchone()[0]
    conn.commit()
    if batch_purged or txn_purged:
        logger.info("Retention purge: %d batch payloads, %d txn raw records nulled (>%d days)",
                     batch_purged, txn_purged, RETENTION_DAYS)
    return batch_purged, txn_purged


def scheduled_sync():
    logger.info("Scheduled sync starting")
    pool = get_pool()
    conn = pool.getconn()
    try:
        result = run_sync(conn)
        logger.info("Scheduled sync result: %s", result)
        try:
            take_balance_snapshot(conn)
        except Exception as e:
            logger.error("Balance snapshot failed: %s", e)
        try:
            purge_old_payloads(conn)
        except Exception as e:
            logger.error("Retention purge failed: %s", e)
    except Exception as e:
        logger.error("Scheduled sync failed: %s", e)
    finally:
        pool.putconn(conn)


# ─────────────────────────────────────────────
# Startup: wait for DB, run immediate sync, then schedule
# ─────────────────────────────────────────────

def wait_for_db():
    logger.info("Waiting for DB...")
    while True:
        try:
            pool = get_pool()
            conn = pool.getconn()
            pool.putconn(conn)
            logger.info("DB ready")
            return
        except Exception as e:
            logger.warning("DB not ready: %s — retrying in 5s", e)
            time.sleep(5)


def main():
    wait_for_db()
    logger.info("Running startup sync")
    scheduled_sync()

    sync_hour   = int(os.environ.get("SYNC_HOUR", "6"))
    sync_minute = int(os.environ.get("SYNC_MINUTE", "0"))

    scheduler = BlockingScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_sync,
        CronTrigger(hour=sync_hour, minute=sync_minute),
        id="daily_sync_am",
        name="Morning SimpleFIN sync + retention purge",
    )
    scheduler.add_job(
        scheduled_sync,
        CronTrigger(hour=18, minute=0),
        id="daily_sync_pm",
        name="Evening SimpleFIN sync",
    )

    logger.info("Scheduler started — syncs at %02d:%02d and 18:00 CT, retention=%d days",
                sync_hour, sync_minute, RETENTION_DAYS)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
