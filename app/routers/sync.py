"""Sync router — trigger, status, log."""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from db import db_conn, db_put
from syncer import run_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])

_sync_running = False


def _take_snapshot_after_sync(conn):
    """Record current account balances — mirrors worker behavior."""
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


def _do_sync(start_date: Optional[date] = None):
    global _sync_running
    _sync_running = True
    conn = db_conn()
    try:
        result = run_sync(conn, start_date)
        if result.get("status") == "ok":
            try:
                _take_snapshot_after_sync(conn)
            except Exception as e:
                logger.error("Balance snapshot failed after manual sync: %s", e)
    except Exception as e:
        logger.error("Manual sync failed: %s", e)
    finally:
        db_put(conn)
        _sync_running = False


class SyncRequest(BaseModel):
    start_date: Optional[date] = None


@router.post("")
def trigger_sync(body: SyncRequest, background_tasks: BackgroundTasks):
    if _sync_running:
        raise HTTPException(status_code=409, detail="Sync already in progress")
    background_tasks.add_task(_do_sync, body.start_date)
    return {"status": "started"}


@router.get("/status")
def sync_status():
    return {"running": _sync_running}


@router.get("/log")
def sync_log(limit: int = 20):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, started_at, finished_at, status, accounts_seen, txns_added, txns_updated, error_message "
            "FROM sync_log ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "started_at": r[1].isoformat() if r[1] else None,
             "finished_at": r[2].isoformat() if r[2] else None,
             "status": r[3], "accounts_seen": r[4], "txns_added": r[5],
             "txns_updated": r[6], "error_message": r[7]} for r in rows]
