"""
Finance Hub v2 — SimpleFIN sync module
Shared by both the worker (scheduled) and the app (manual trigger via API).

Flow:
  1. Read ACCESS_URL from /run/secrets/simplefin_access_url
  2. GET {ACCESS_URL}/accounts?start-date=<epoch>
  3. Create import_batch record + store raw payload
  4. Upsert accounts
  5. Upsert transactions (skip category_id if category_manual=True)
     - Tag new txns with import_batch_id
     - Detect near-duplicates and flag for review
  6. Apply payee rules to any uncategorized transactions
  7. Close import_batch + sync_log rows
"""

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import psycopg2

logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
except ImportError:
    CT = None


def read_secret(name: str) -> str:
    p = Path(f"/run/secrets/{name}")
    if p.exists(): return p.read_text().strip()
    import os
    val = os.environ.get(name.upper())
    if val: return val
    raise RuntimeError(f"Secret '{name}' not found in /run/secrets or env")

def _redact_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.hostname}:***"
    except Exception: return "<redacted>"

def _epoch_to_date(epoch: int) -> date:
    if CT is not None: return datetime.fromtimestamp(epoch, tz=CT).date()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).date()

def _epoch_to_datetime(epoch: int) -> datetime:
    if CT is not None: return datetime.fromtimestamp(epoch, tz=CT)
    return datetime.fromtimestamp(epoch, tz=timezone.utc)

SYNC_LOCK_ID = 7355608

def acquire_sync_lock(conn) -> bool:
    cur = conn.cursor(); cur.execute("SELECT pg_try_advisory_lock(%s)", (SYNC_LOCK_ID,)); return cur.fetchone()[0]

def release_sync_lock(conn):
    try: cur = conn.cursor(); cur.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_ID,))
    except Exception: pass

def fetch_simplefin(start_date: Optional[date] = None) -> dict:
    access_url = read_secret("simplefin_access_url").rstrip("/")
    if start_date is None: start_date = date.today() - timedelta(days=90)
    start_epoch = int(datetime(start_date.year, start_date.month, start_date.day).timestamp())
    url = f"{access_url}/accounts"; params = {"start-date": start_epoch}
    logger.info("Fetching SimpleFIN: %s start-date=%s", _redact_url(url), start_date)
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, params=params); resp.raise_for_status()
    data = resp.json()
    for err in data.get("errors", []): logger.warning("SimpleFIN error: %s", err)
    return data

def apply_payee_rules(cur, txn_ids: list[str] = None) -> int:
    cur.execute("SELECT id, match_pattern, payee_name, category_id FROM payee_rules WHERE deleted_at IS NULL ORDER BY priority DESC, id")
    rules = cur.fetchall()
    if not rules: return 0
    if txn_ids:
        placeholders = ",".join(["%s"] * len(txn_ids))
        cur.execute(f"SELECT id, description, payee FROM transactions WHERE id IN ({placeholders}) AND category_id IS NULL AND category_manual = FALSE", txn_ids)
    else:
        cur.execute("SELECT id, description, payee FROM transactions WHERE category_id IS NULL AND category_manual = FALSE")
    txns = cur.fetchall()
    if not txns: return 0
    categorized = 0
    for txn_id, description, payee in txns:
        search_text = " ".join(filter(None, [(description or "").lower(), (payee or "").lower()]))
        if not search_text.strip(): continue
        for rule_id, pattern, payee_name, category_id in rules:
            if pattern and pattern.lower() in search_text:
                cur.execute("UPDATE transactions SET category_id = %s, payee = COALESCE(%s, payee), updated_at = NOW() WHERE id = %s AND category_manual = FALSE", (category_id, payee_name, txn_id))
                categorized += 1; break
    return categorized

def detect_near_dupes(cur, txn_id: str, account_id: str, amount: float, posted: date, batch_id: int) -> bool:
    cur.execute("SELECT id, posted, amount, description FROM transactions WHERE account_id = %s AND id != %s AND ABS(amount - %s) < 0.02 AND posted BETWEEN %s AND %s LIMIT 1",
        (account_id, txn_id, amount, posted - timedelta(days=1), posted + timedelta(days=1)))
    existing = cur.fetchone()
    if existing:
        dup_id, dup_posted, dup_amount, dup_desc = existing
        reason = f"Same account, amount ${abs(amount):.2f} vs ${abs(float(dup_amount)):.2f}, dates {posted} vs {dup_posted}"
        cur.execute("INSERT INTO duplicate_flags (txn_id, duplicate_of, reason, status, batch_id) VALUES (%s, %s, %s, 'pending', %s) ON CONFLICT DO NOTHING", (txn_id, dup_id, reason, batch_id))
        logger.info("Flagged near-dupe: %s <-> %s (%s)", txn_id, dup_id, reason); return True
    return False

def run_sync(conn: psycopg2.extensions.connection, start_date: Optional[date] = None) -> dict:
    if not acquire_sync_lock(conn):
        logger.warning("Sync skipped — another sync is already running (advisory lock held)")
        return {"status": "skipped", "reason": "lock_held"}
    cur = conn.cursor()
    cur.execute("INSERT INTO import_batches (status, source) VALUES ('running', 'simplefin') RETURNING id")
    batch_id = cur.fetchone()[0]
    cur.execute("INSERT INTO sync_log (status) VALUES ('running') RETURNING id")
    log_id = cur.fetchone()[0]; conn.commit()
    accounts_seen = txns_added = txns_updated = txns_skipped = dupes_flagged = 0
    try:
        data = fetch_simplefin(start_date); new_txn_ids = []
        cur.execute("UPDATE import_batches SET raw_payload = %s WHERE id = %s", (json.dumps(data), batch_id)); conn.commit()
        for acct in data.get("accounts", []):
            accounts_seen += 1; acct_id = acct["id"]; org = acct.get("org", {})
            balance_raw = acct.get("balance"); balance_date_raw = acct.get("balance-date")
            balance = float(balance_raw) if balance_raw is not None else None
            balance_dt = _epoch_to_datetime(balance_date_raw) if balance_date_raw else None
            cur.execute("""INSERT INTO accounts (id, name, currency, balance, balance_date, org_name, org_domain) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, balance=EXCLUDED.balance, balance_date=EXCLUDED.balance_date, org_name=EXCLUDED.org_name, org_domain=EXCLUDED.org_domain, updated_at=NOW()""",
                (acct_id, acct.get("name", acct_id), acct.get("currency", "USD"), balance, balance_dt, org.get("name"), org.get("domain")))
            for txn in acct.get("transactions", []):
                txn_id = txn["id"]; posted_raw = txn.get("posted") or txn.get("transacted_at")
                posted = _epoch_to_date(posted_raw) if posted_raw else date.today()
                amount = float(txn.get("amount", 0)); description = txn.get("description", "").strip(); pending = txn.get("pending", False)
                cur.execute("SELECT id, category_manual FROM transactions WHERE id = %s", (txn_id,))
                existing = cur.fetchone()
                if existing is None:
                    cur.execute("INSERT INTO transactions (id, account_id, posted, amount, description, pending, raw, import_batch_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (txn_id, acct_id, posted, amount, description, pending, json.dumps(txn), batch_id))
                    new_txn_ids.append(txn_id); txns_added += 1
                    if detect_near_dupes(cur, txn_id, acct_id, amount, posted, batch_id): dupes_flagged += 1
                else:
                    # P1 fix: update all mutable fields including posted date,
                    # account_id (in case upstream corrects), and import_batch_id
                    # for provenance tracking. Never overwrite user-set fields.
                    cur.execute(
                        """UPDATE transactions SET
                             posted          = %s,
                             amount          = %s,
                             description     = %s,
                             pending         = %s,
                             account_id      = %s,
                             raw             = %s,
                             import_batch_id = %s,
                             updated_at      = NOW()
                           WHERE id = %s""",
                        (posted, amount, description, pending, acct_id,
                         json.dumps(txn), batch_id, txn_id))
                    txns_updated += 1
        conn.commit(); categorized = apply_payee_rules(cur); conn.commit()
        logger.info("Sync complete: batch=%d accounts=%d added=%d updated=%d dupes_flagged=%d auto-categorized=%d", batch_id, accounts_seen, txns_added, txns_updated, dupes_flagged, categorized)
        cur.execute("UPDATE import_batches SET status='ok', finished_at=NOW(), accounts_seen=%s, txns_added=%s, txns_updated=%s, txns_skipped=%s, dupes_flagged=%s WHERE id=%s",
            (accounts_seen, txns_added, txns_updated, txns_skipped, dupes_flagged, batch_id))
        cur.execute("UPDATE sync_log SET status='ok', finished_at=NOW(), accounts_seen=%s, txns_added=%s, txns_updated=%s WHERE id=%s",
            (accounts_seen, txns_added, txns_updated, log_id))
        conn.commit()
        return {"status": "ok", "batch_id": batch_id, "accounts_seen": accounts_seen, "txns_added": txns_added, "txns_updated": txns_updated, "txns_skipped": txns_skipped, "dupes_flagged": dupes_flagged, "auto_categorized": categorized}
    except Exception as exc:
        conn.rollback(); logger.error("Sync failed: %s", exc, exc_info=True)
        cur.execute("UPDATE import_batches SET status='error', finished_at=NOW(), error_message=%s WHERE id=%s", (str(exc), batch_id))
        cur.execute("UPDATE sync_log SET status='error', finished_at=NOW(), error_message=%s WHERE id=%s", (str(exc), log_id))
        conn.commit(); raise
    finally:
        release_sync_lock(conn)
