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
        FROM accounts WHERE hidden = FALSE AND on_budget = TRUE AND balance IS NOT NULL
        ON CONFLICT (snapshot_date, account_id) DO UPDATE SET
            balance = EXCLUDED.balance,
            account_name = EXCLUDED.account_name,
            account_type = EXCLUDED.account_type
    """, (today,))
    count = cur.rowcount
    conn.commit()
    logger.info("Balance snapshot: %d accounts for %s", count, today)
    return count


def take_goal_snapshot(conn):
    """Snapshot progress for all active savings goals."""
    cur = conn.cursor()
    today = date.today()
    cur.execute("""
        INSERT INTO goal_snapshots (goal_id, snapshot_date, amount)
        SELECT g.id, %s,
               CASE WHEN g.account_id IS NOT NULL AND a.balance IS NOT NULL
                    THEN a.balance
                    ELSE COALESCE(g.current_amount, 0)
               END
        FROM savings_goals g
        LEFT JOIN accounts a ON g.account_id = a.id
        WHERE g.status = 'active'
        ON CONFLICT (goal_id, snapshot_date) DO UPDATE SET
            amount = EXCLUDED.amount
    """, (today,))
    count = cur.rowcount
    conn.commit()
    if count:
        logger.info("Goal snapshot: %d goals for %s", count, today)
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


def refresh_holding_prices(conn):
    """Fetch latest prices from Yahoo Finance using Ticker API."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM holdings")
    tickers = [r[0] for r in cur.fetchall()]
    if not tickers:
        return 0
    try:
        import yfinance as yf
        from datetime import datetime as dt_now
        updated = 0
        now = dt_now.now()
        for ticker in tickers:
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="5d")
                if len(hist) > 0:
                    price = float(hist["Close"].iloc[-1])
                    cur.execute("UPDATE holdings SET last_price = %s, last_price_date = %s WHERE ticker = %s",
                                (price, now, ticker))
                    updated += cur.rowcount
            except Exception as e:
                logger.warning("Price fetch %s: %s", ticker, e)
        today = date.today()
        cur.execute("""
            INSERT INTO holding_snapshots (snapshot_date, holding_id, price, market_value)
            SELECT %s, h.id, h.last_price, h.shares * h.last_price
            FROM holdings h WHERE h.last_price IS NOT NULL
            ON CONFLICT (snapshot_date, holding_id) DO UPDATE SET
                price = EXCLUDED.price, market_value = EXCLUDED.market_value
        """, (today,))
        conn.commit()
        logger.info("Price refresh: %d/%d tickers updated", updated, len(tickers))
        return updated
    except Exception as e:
        logger.error("Price refresh failed: %s", e)
        return 0


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
            refresh_holding_prices(conn)
        except Exception as e:
            logger.error("Holding price refresh failed: %s", e)
        # Refresh benchmark prices (SPY, VTI, QQQ)
        try:
            cur = conn.cursor()
            for bench_ticker in ["SPY", "VTI", "QQQ"]:
                try:
                    import yfinance as yf
                    tk = yf.Ticker(bench_ticker)
                    hist = tk.history(period="1mo", interval="1d")
                    for idx, row in hist.iterrows():
                        d = idx.date() if hasattr(idx, 'date') else idx
                        cur.execute(
                            "INSERT INTO benchmark_prices (ticker, price_date, close_price) "
                            "VALUES (%s, %s, %s) ON CONFLICT (ticker, price_date) DO UPDATE SET close_price = EXCLUDED.close_price",
                            (bench_ticker, d, float(row["Close"])))
                except Exception as e:
                    logger.warning("Benchmark %s refresh failed: %s", bench_ticker, e)
            conn.commit()
            logger.info("Benchmark prices refreshed")
        except Exception as e:
            logger.error("Benchmark refresh failed: %s", e)
        try:
            take_goal_snapshot(conn)
        except Exception as e:
            logger.error("Goal snapshot failed: %s", e)
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


def send_monthly_digest():
    """Send monthly spending digest to Telegram on the 1st of each month."""
    import os
    from pathlib import Path

    token_path = Path("/run/secrets/telegram_bot_token")
    if token_path.exists():
        bot_token = token_path.read_text().strip()
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.warning("Telegram not configured — skipping monthly digest")
        return

    pool = get_pool()
    conn = pool.getconn()
    try:
        import httpx
        import calendar
        from datetime import datetime as dt_cls

        # Last month
        today = date.today()
        first_of_this = date(today.year, today.month, 1)
        last_month_end = first_of_this - timedelta(days=1)
        yr, mo = last_month_end.year, last_month_end.month
        last_day = calendar.monthrange(yr, mo)[1]
        start = date(yr, mo, 1)
        end = date(yr, mo, last_day)
        label = f"{yr}-{mo:02d}"

        cur = conn.cursor()

        # Income
        cur.execute(
            "SELECT COALESCE(SUM(t.amount), 0) FROM transactions t "
            "LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.is_income, FALSE) = TRUE "
            "AND t.posted >= %s AND t.posted <= %s", (start, end))
        income = float(cur.fetchone()[0])

        # Spending
        cur.execute(
            "SELECT COALESCE(SUM(ABS(t.amount)), 0) FROM spending_items t "
            "LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s", (start, end))
        spending = float(cur.fetchone()[0])

        net = income - spending
        rate = ((income - spending) / income * 100) if income > 0 else 0

        # Top 5 categories
        cur.execute(
            "SELECT COALESCE(c.name, 'Other'), SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s "
            "GROUP BY c.name ORDER BY 2 DESC LIMIT 5", (start, end))
        top_cats = [(r[0], float(r[1])) for r in cur.fetchall()]

        # Net worth
        cur.execute(
            "SELECT SUM(balance) FROM balance_snapshots WHERE snapshot_date = ("
            "SELECT MAX(snapshot_date) FROM balance_snapshots WHERE snapshot_date <= %s)", (end,))
        nw = cur.fetchone()
        nw_val = float(nw[0]) if nw and nw[0] else None

        # Format message
        lines = [
            f"\U0001f4b0 *Finance Hub — {label} Digest*",
            "",
            f"\U0001f4ca *Summary*",
            f"  Income: ${income:,.2f}",
            f"  Spending: ${spending:,.2f}",
            f"  Net: {'\u2705' if net >= 0 else '\U0001f534'} ${net:,.2f}",
            f"  Savings rate: {rate:.1f}%",
        ]
        if top_cats:
            lines += ["", "\U0001f3f7 *Top Spending*"]
            for i, (cat, amt) in enumerate(top_cats, 1):
                lines.append(f"  {i}. {cat}: ${amt:,.2f}")
        if nw_val is not None:
            lines += ["", f"\U0001f4c8 Net Worth: ${nw_val:,.2f}"]
        lines += ["", "_Generated by Finance Hub_"]
        text = "\n".join(lines)

        # Send
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json={
                "chat_id": chat_id, "text": text,
                "parse_mode": "Markdown", "disable_web_page_preview": True,
            })
            resp.raise_for_status()
        logger.info("Monthly digest sent to Telegram for %s", label)

    except Exception as e:
        logger.error("Monthly digest failed: %s", e, exc_info=True)
    finally:
        pool.putconn(conn)


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

    # Monthly digest: 1st of each month at 9AM CT
    scheduler.add_job(
        send_monthly_digest,
        CronTrigger(day=1, hour=9, minute=0),
        id="monthly_digest",
        name="Monthly spending digest to Telegram",
    )

    logger.info("Scheduler started — syncs at %02d:%02d and 18:00 CT, retention=%d days",
                sync_hour, sync_minute, RETENTION_DAYS)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
