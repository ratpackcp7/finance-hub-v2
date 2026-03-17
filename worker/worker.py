"""
Finance Hub v2 — Background Worker
Runs a daily SimpleFIN sync via APScheduler. No Redis, no webhooks.
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

# syncer.py is shared — copied into worker container at build time
from syncer import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


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
# Scheduled job
# ─────────────────────────────────────────────

def scheduled_sync():
    logger.info("Scheduled sync starting")
    pool = get_pool()
    conn = pool.getconn()
    try:
        result = run_sync(conn)
        logger.info("Scheduled sync result: %s", result)
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

    # Run an immediate sync on startup so data is fresh right away
    logger.info("Running startup sync")
    scheduled_sync()

    # Schedule daily sync
    sync_hour   = int(os.environ.get("SYNC_HOUR", "6"))
    sync_minute = int(os.environ.get("SYNC_MINUTE", "0"))

    scheduler = BlockingScheduler(timezone="America/Chicago")
    scheduler.add_job(
        scheduled_sync,
        CronTrigger(hour=sync_hour, minute=sync_minute),
        id="daily_sync",
        name="Daily SimpleFIN sync",
    )

    logger.info("Scheduler started — daily sync at %02d:%02d CT", sync_hour, sync_minute)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
