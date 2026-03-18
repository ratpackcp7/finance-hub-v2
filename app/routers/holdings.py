"""Holdings router — CRUD, price fetch, dividend tracking, deviation alerts."""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import db_conn, db_put

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/holdings", tags=["holdings"])


class HoldingCreate(BaseModel):
    account_id: str
    ticker: str
    name: str
    shares: float = 0
    cost_basis: Optional[float] = None


class HoldingUpdate(BaseModel):
    name: Optional[str] = None
    shares: Optional[float] = None
    cost_basis: Optional[float] = None


@router.get("")
def list_holdings():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT h.id, h.account_id, a.name AS account_name, h.ticker, h.name,
                   h.shares, h.cost_basis, h.last_price, h.last_price_date, h.updated_at
            FROM holdings h
            JOIN accounts a ON a.id = h.account_id
            ORDER BY (h.shares * COALESCE(h.last_price, 0)) DESC NULLS LAST
        """)
        rows = cur.fetchall()
    finally:
        db_put(conn)
    holdings = []
    for r in rows:
        shares = float(r[5]) if r[5] else 0
        price = float(r[7]) if r[7] else None
        basis = float(r[6]) if r[6] else None
        market_val = shares * price if shares and price else None
        total_cost = basis * shares if basis and shares else None
        gain = (market_val - total_cost) if market_val is not None and total_cost else None
        gain_pct = (gain / total_cost * 100) if gain is not None and total_cost and total_cost > 0 else None
        holdings.append({
            "id": r[0], "account_id": r[1], "account_name": r[2],
            "ticker": r[3], "name": r[4], "shares": shares,
            "cost_basis": basis, "last_price": price,
            "last_price_date": r[8].isoformat() if r[8] else None,
            "market_value": round(market_val, 2) if market_val is not None else None,
            "gain": round(gain, 2) if gain is not None else None,
            "gain_pct": round(gain_pct, 2) if gain_pct is not None else None,
        })
    total_value = sum(h["market_value"] or 0 for h in holdings)
    total_cost = sum((h["cost_basis"] or 0) * h["shares"] for h in holdings)
    total_gain = total_value - total_cost if total_cost > 0 else None
    return {
        "holdings": holdings,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_gain": round(total_gain, 2) if total_gain is not None else None,
    }


@router.post("")
def create_holding(body: HoldingCreate):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE id = %s", (body.account_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Account not found")
        cur.execute("""
            INSERT INTO holdings (account_id, ticker, name, shares, cost_basis)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (account_id, ticker) DO UPDATE SET
                name = EXCLUDED.name, shares = EXCLUDED.shares,
                cost_basis = EXCLUDED.cost_basis, updated_at = NOW()
            RETURNING id
        """, (body.account_id, body.ticker.upper(), body.name, body.shares, body.cost_basis))
        hid = cur.fetchone()[0]
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "id": hid}


@router.patch("/{holding_id}")
def update_holding(holding_id: int, body: HoldingUpdate):
    conn = db_conn()
    try:
        cur = conn.cursor()
        sets, vals = [], []
        if body.name is not None:
            sets.append("name = %s"); vals.append(body.name)
        if body.shares is not None:
            sets.append("shares = %s"); vals.append(body.shares)
        if body.cost_basis is not None:
            sets.append("cost_basis = %s"); vals.append(body.cost_basis)
        if not sets:
            return {"status": "ok"}
        sets.append("updated_at = NOW()")
        vals.append(holding_id)
        cur.execute(f"UPDATE holdings SET {', '.join(sets)} WHERE id = %s", vals)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


@router.delete("/{holding_id}")
def delete_holding(holding_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM holdings WHERE id = %s", (holding_id,))
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


@router.post("/refresh-prices")
def refresh_prices():
    """Fetch latest prices from Yahoo Finance using Ticker API (handles mutual funds)."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM holdings")
        tickers = [r[0] for r in cur.fetchall()]
        if not tickers:
            return {"status": "ok", "updated": 0}

        import yfinance as yf
        updated = 0
        now = datetime.now()
        errors = []

        for ticker in tickers:
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="5d")
                if len(hist) > 0:
                    price = float(hist["Close"].iloc[-1])
                    cur.execute("UPDATE holdings SET last_price = %s, last_price_date = %s WHERE ticker = %s",
                                (price, now, ticker))
                    updated += cur.rowcount
                else:
                    errors.append(f"{ticker}: no data")
            except Exception as e:
                errors.append(f"{ticker}: {str(e)[:50]}")

        # Take holding snapshots
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
    finally:
        db_put(conn)
    result = {"status": "ok", "updated": updated, "tickers": len(tickers)}
    if errors:
        result["errors"] = errors
    return result


# ── Dividend & Reinvestment Tracking ──

# Map transaction payees to tickers
PAYEE_TICKER_MAP = {
    "cohen steers reit": "RNP",
    "nvidia corp": "NVDA",
    "meta platforms inc": "META",
    "vanguard mega cap growth": "MGK",
    "vanguard total stock market etf": "VTI",
    "vanguard total stock market index admiral": "VTSAX",
    "vanguard growth index": "VITAX",
    "fidelity wise origin bitcoin": "FBTC",
    "state street spdr": "SPYM",
    "vanguard federal money market": "VMFXX",
}


@router.get("/activity")
def holding_activity(months: int = 6):
    """Match investment transactions to holdings. Show dividends, reinvestments, and unmatched activity."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)

        # Get all investment account transactions
        cur.execute("""
            SELECT t.id, t.posted, t.payee, t.description, t.amount, t.account_id, a.name AS account_name
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.account_type IN ('investment', 'retirement', 'brokerage')
            AND t.posted >= %s
            ORDER BY t.posted DESC
        """, (cutoff,))
        txns = cur.fetchall()

        # Get holdings
        cur.execute("SELECT id, account_id, ticker, name FROM holdings")
        holdings = cur.fetchall()
        holding_map = {(h[1], h[2]): {"id": h[0], "ticker": h[2], "name": h[3]} for h in holdings}
    finally:
        db_put(conn)

    dividends = []
    reinvestments = []
    unmatched = []

    for txn_id, posted, payee, desc, amount, acct_id, acct_name in txns:
        payee_lower = (payee or desc or "").lower()
        amount = float(amount)

        # Try to match to a holding via payee
        matched_ticker = None
        for pattern, ticker in PAYEE_TICKER_MAP.items():
            if pattern in payee_lower:
                matched_ticker = ticker
                break

        entry = {
            "txn_id": txn_id,
            "date": posted.isoformat()[:10] if posted else None,
            "payee": payee or desc,
            "amount": amount,
            "account_id": acct_id,
            "account_name": acct_name,
            "matched_ticker": matched_ticker,
        }

        if matched_ticker:
            if amount > 0:
                dividends.append(entry)
            else:
                reinvestments.append(entry)
        else:
            unmatched.append(entry)

    # Aggregate dividends by ticker by month
    div_by_ticker = {}
    for d in dividends:
        t = d["matched_ticker"]
        m = d["date"][:7] if d["date"] else "?"
        key = (t, m)
        if key not in div_by_ticker:
            div_by_ticker[key] = {"ticker": t, "month": m, "total": 0, "count": 0}
        div_by_ticker[key]["total"] += d["amount"]
        div_by_ticker[key]["count"] += 1

    return {
        "dividends": dividends,
        "reinvestments": reinvestments,
        "unmatched": unmatched,
        "dividend_summary": sorted(div_by_ticker.values(), key=lambda x: (x["month"], x["ticker"]), reverse=True),
        "totals": {
            "dividend_income": sum(d["amount"] for d in dividends),
            "reinvested": sum(r["amount"] for r in reinvestments),
            "net": sum(d["amount"] for d in dividends) + sum(r["amount"] for r in reinvestments),
        }
    }


@router.get("/alerts")
def holding_alerts():
    """Detect deviations: account balance vs holdings value, unexpected transactions, missing dividends."""
    conn = db_conn()
    try:
        cur = conn.cursor()

        # Get accounts with holdings
        cur.execute("""
            SELECT a.id, a.name, a.balance, a.account_type,
                   COALESCE(SUM(h.shares * h.last_price), 0) AS holdings_value,
                   COUNT(h.id) AS holding_count
            FROM accounts a
            LEFT JOIN holdings h ON h.account_id = a.id AND h.last_price IS NOT NULL
            WHERE a.account_type IN ('investment', 'retirement', 'brokerage')
            AND a.hidden = FALSE
            GROUP BY a.id, a.name, a.balance, a.account_type
        """)
        acct_rows = cur.fetchall()

        # Get recent unmatched transactions (last 30 days)
        cutoff = date.today() - timedelta(days=30)
        cur.execute("""
            SELECT t.posted, t.payee, t.description, t.amount, a.name
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE a.account_type IN ('investment', 'retirement', 'brokerage')
            AND t.posted >= %s
            ORDER BY t.posted DESC
        """, (cutoff,))
        recent_txns = cur.fetchall()

        # Check for expected monthly dividends that haven't appeared
        cur.execute("""
            SELECT h.ticker, h.name, h.account_id
            FROM holdings h WHERE h.shares > 0
        """)
        active_holdings = cur.fetchall()
    finally:
        db_put(conn)

    alerts = []

    # 1. Account balance vs holdings value mismatch
    for acct_id, acct_name, balance, acct_type, holdings_val, holding_count in acct_rows:
        balance = float(balance) if balance else 0
        holdings_val = float(holdings_val)

        if holding_count == 0 and balance > 100:
            alerts.append({
                "type": "no_holdings",
                "severity": "warning",
                "account": acct_name,
                "message": f"Account has ${balance:,.2f} balance but no holdings tracked. Add holdings to track this account.",
            })
        elif holding_count > 0 and holdings_val > 0:
            diff = abs(balance - holdings_val)
            pct = (diff / balance * 100) if balance != 0 else 0
            if pct > 10 and diff > 500:
                alerts.append({
                    "type": "balance_mismatch",
                    "severity": "warning",
                    "account": acct_name,
                    "message": f"Account balance ${balance:,.2f} vs tracked holdings ${holdings_val:,.2f} — gap of ${diff:,.2f} ({pct:.0f}%). Share counts may need updating.",
                    "account_balance": balance,
                    "holdings_value": holdings_val,
                    "gap": diff,
                    "gap_pct": round(pct, 1),
                })

    # 2. Unmatched recent transactions
    for posted, payee, desc, amount, acct_name in recent_txns:
        payee_lower = (payee or desc or "").lower()
        matched = any(p in payee_lower for p in PAYEE_TICKER_MAP)
        if not matched and abs(float(amount)) > 1:
            alerts.append({
                "type": "unmatched_txn",
                "severity": "info",
                "account": acct_name,
                "message": f"Unrecognized activity: {payee or desc} (${float(amount):,.2f}) on {posted.isoformat()[:10]}. May indicate a new holding or activity not tracked.",
                "date": posted.isoformat()[:10],
                "amount": float(amount),
            })

    # 3. Zero-share holdings with prices (placeholder entries)
    for ticker, name, acct_id in active_holdings:
        pass  # These are expected — user hasn't entered shares yet

    # Deduplicate unmatched txn alerts (same payee pairs cancel out)
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/history")
def holdings_history(months: int = 6):
    """Daily portfolio value from holding snapshots."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)
        cur.execute("""
            SELECT hs.snapshot_date, h.ticker, h.name, hs.price, hs.market_value
            FROM holding_snapshots hs
            JOIN holdings h ON h.id = hs.holding_id
            WHERE hs.snapshot_date >= %s
            ORDER BY hs.snapshot_date ASC, hs.market_value DESC
        """, (cutoff,))
        rows = cur.fetchall()
    finally:
        db_put(conn)
    by_date = {}
    for snap_date, ticker, name, price, mv in rows:
        d = snap_date.isoformat()
        if d not in by_date:
            by_date[d] = {"date": d, "total": 0, "holdings": []}
        by_date[d]["total"] += float(mv) if mv else 0
        by_date[d]["holdings"].append({
            "ticker": ticker, "name": name,
            "price": float(price) if price else None,
            "value": float(mv) if mv else None
        })
    return {"history": sorted(by_date.values(), key=lambda x: x["date"])}
