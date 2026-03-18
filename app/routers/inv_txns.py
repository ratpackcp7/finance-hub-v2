"""Investment transactions router — buy/sell/dividend/reinvest CRUD + dividend income."""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_conn, db_put

router = APIRouter(prefix="/api/investment-txns", tags=["investments"])

VALID_TYPES = {"buy", "sell", "dividend", "reinvest", "fee", "split", "transfer_in", "transfer_out"}


class InvTxnCreate(BaseModel):
    holding_id: int
    txn_type: str
    txn_date: str
    shares: Optional[float] = None
    price_per_share: Optional[float] = None
    total_amount: float
    fees: Optional[float] = 0
    notes: Optional[str] = None


@router.get("")
def list_investment_txns(holding_id: Optional[int] = None, account_id: Optional[str] = None,
                         txn_type: Optional[str] = None, limit: int = 100):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters = ["1=1"]
        params = []
        if holding_id:
            filters.append("it.holding_id = %s"); params.append(holding_id)
        if account_id:
            filters.append("it.account_id = %s"); params.append(account_id)
        if txn_type:
            filters.append("it.txn_type = %s"); params.append(txn_type)
        cur.execute(
            f"""SELECT it.id, it.holding_id, h.ticker, h.name, it.account_id,
                       it.txn_type, it.txn_date, it.shares, it.price_per_share,
                       it.total_amount, it.fees, it.notes, it.source
                FROM investment_transactions it
                JOIN holdings h ON it.holding_id = h.id
                WHERE {' AND '.join(filters)}
                ORDER BY it.txn_date DESC, it.id DESC
                LIMIT %s""", params + [limit])
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "holding_id": r[1], "ticker": r[2], "holding_name": r[3],
             "account_id": r[4], "type": r[5],
             "date": r[6].isoformat() if r[6] else None,
             "shares": float(r[7]) if r[7] else None,
             "price_per_share": float(r[8]) if r[8] else None,
             "total_amount": float(r[9]), "fees": float(r[10]) if r[10] else 0,
             "notes": r[11], "source": r[12]} for r in rows]


@router.post("", status_code=201)
def create_investment_txn(body: InvTxnCreate):
    if body.txn_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"txn_type must be: {', '.join(sorted(VALID_TYPES))}")
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, account_id FROM holdings WHERE id = %s", (body.holding_id,))
        h = cur.fetchone()
        if not h:
            raise HTTPException(status_code=404, detail="Holding not found")

        cur.execute(
            "INSERT INTO investment_transactions "
            "(holding_id, account_id, txn_type, txn_date, shares, price_per_share, total_amount, fees, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (body.holding_id, h[1], body.txn_type, body.txn_date,
             body.shares, body.price_per_share, body.total_amount,
             body.fees or 0, body.notes))
        txn_id = cur.fetchone()[0]

        # Auto-create tax lot for buys
        if body.txn_type == "buy" and body.shares and body.price_per_share:
            basis = round(body.shares * body.price_per_share, 2)
            cur.execute(
                "INSERT INTO tax_lots (holding_id, inv_txn_id, open_date, shares_purchased, "
                "cost_basis_per_share, shares_remaining, basis_remaining) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (body.holding_id, txn_id, body.txn_date,
                 body.shares, body.price_per_share, body.shares, basis))

        # Auto-close lots for sells (FIFO)
        if body.txn_type == "sell" and body.shares and body.shares > 0:
            _close_lots_fifo(cur, body.holding_id, body.shares,
                            body.price_per_share or 0, body.txn_date)

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_put(conn)
    return {"id": txn_id, "type": body.txn_type}


@router.delete("/{txn_id}")
def delete_investment_txn(txn_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Remove associated tax lot if it's a buy
        cur.execute("DELETE FROM tax_lots WHERE inv_txn_id = %s", (txn_id,))
        cur.execute("DELETE FROM investment_transactions WHERE id = %s", (txn_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok"}


def _close_lots_fifo(cur, holding_id, shares_to_sell, sell_price, sell_date):
    """Close tax lots using FIFO method."""
    cur.execute(
        "SELECT id, shares_remaining, cost_basis_per_share, open_date "
        "FROM tax_lots WHERE holding_id = %s AND shares_remaining > 0 "
        "ORDER BY open_date ASC", (holding_id,))
    lots = cur.fetchall()
    remaining = shares_to_sell
    for lot_id, lot_shares, lot_basis, open_date in lots:
        if remaining <= 0:
            break
        close_qty = min(remaining, float(lot_shares))
        new_remaining = float(lot_shares) - close_qty
        gain = round(close_qty * (sell_price - float(lot_basis)), 2)
        is_long = (sell_date - open_date).days > 365 if sell_date and open_date else None
        if new_remaining < 0.0001:
            cur.execute(
                "UPDATE tax_lots SET shares_remaining = 0, basis_remaining = 0, "
                "closed_date = %s, close_price = %s, realized_gain = %s, is_long_term = %s "
                "WHERE id = %s", (sell_date, sell_price, gain, is_long, lot_id))
        else:
            new_basis = round(new_remaining * float(lot_basis), 2)
            cur.execute(
                "UPDATE tax_lots SET shares_remaining = %s, basis_remaining = %s WHERE id = %s",
                (new_remaining, new_basis, lot_id))
        remaining -= close_qty


# ── Dividend Income ──

@router.get("/dividends")
def dividend_income(months: int = 12, holding_id: Optional[int] = None):
    """Dividend income by month and holding."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)
        filters = ["it.txn_type = 'dividend'", "it.txn_date >= %s"]
        params = [cutoff]
        if holding_id:
            filters.append("it.holding_id = %s"); params.append(holding_id)

        # By month
        cur.execute(
            f"""SELECT DATE_TRUNC('month', it.txn_date)::date, SUM(it.total_amount)
                FROM investment_transactions it
                WHERE {' AND '.join(filters)}
                GROUP BY 1 ORDER BY 1""", params)
        monthly = [{"month": r[0].strftime("%Y-%m"), "amount": float(r[1])} for r in cur.fetchall()]

        # By holding
        cur.execute(
            f"""SELECT h.ticker, h.name, SUM(it.total_amount), COUNT(*)
                FROM investment_transactions it
                JOIN holdings h ON it.holding_id = h.id
                WHERE {' AND '.join(filters)}
                GROUP BY h.ticker, h.name ORDER BY 3 DESC""", params)
        by_holding = [{"ticker": r[0], "name": r[1], "total": float(r[2]), "payments": r[3]} for r in cur.fetchall()]

        total = sum(m["amount"] for m in monthly)
        annual_est = (total / months * 12) if months > 0 else 0
    finally:
        db_put(conn)
    return {"monthly": monthly, "by_holding": by_holding,
            "total": round(total, 2), "annual_estimate": round(annual_est, 2),
            "months": months}


# ── Tax Lots / Gain-Loss ──

@router.get("/lots/{holding_id}")
def get_lots(holding_id: int, include_closed: bool = False):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters = ["tl.holding_id = %s"]
        params = [holding_id]
        if not include_closed:
            filters.append("tl.shares_remaining > 0")
        cur.execute(
            f"""SELECT tl.id, tl.open_date, tl.shares_purchased, tl.cost_basis_per_share,
                       tl.shares_remaining, tl.basis_remaining, tl.closed_date,
                       tl.close_price, tl.realized_gain, tl.is_long_term
                FROM tax_lots tl WHERE {' AND '.join(filters)}
                ORDER BY tl.open_date ASC""", params)
        rows = cur.fetchall()
    finally:
        db_put(conn)
    return [{"id": r[0], "open_date": r[1].isoformat() if r[1] else None,
             "shares_purchased": float(r[2]), "cost_basis_per_share": float(r[3]),
             "shares_remaining": float(r[4]), "basis_remaining": float(r[5]),
             "closed_date": r[6].isoformat() if r[6] else None,
             "close_price": float(r[7]) if r[7] else None,
             "realized_gain": float(r[8]) if r[8] else None,
             "is_long_term": r[9]} for r in rows]


@router.get("/gains")
def gains_summary():
    """Unrealized + realized gain/loss across all holdings."""
    conn = db_conn()
    try:
        cur = conn.cursor()
        # Unrealized: open lots vs current price
        cur.execute(
            """SELECT h.id, h.ticker, h.name, h.last_price, h.cost_basis,
                      h.shares, a.name as account_name,
                      COALESCE(SUM(tl.shares_remaining), 0) as lot_shares,
                      COALESCE(SUM(tl.basis_remaining), 0) as lot_basis
               FROM holdings h
               JOIN accounts a ON h.account_id = a.id
               LEFT JOIN tax_lots tl ON tl.holding_id = h.id AND tl.shares_remaining > 0
               GROUP BY h.id, h.ticker, h.name, h.last_price, h.cost_basis, h.shares, a.name
               ORDER BY h.shares * COALESCE(h.last_price, 0) DESC""")
        holdings = cur.fetchall()

        # Realized gains from closed lots
        cur.execute(
            "SELECT COALESCE(SUM(realized_gain), 0), "
            "COALESCE(SUM(CASE WHEN is_long_term THEN realized_gain ELSE 0 END), 0), "
            "COALESCE(SUM(CASE WHEN NOT is_long_term THEN realized_gain ELSE 0 END), 0) "
            "FROM tax_lots WHERE closed_date IS NOT NULL")
        realized = cur.fetchone()
    finally:
        db_put(conn)

    items = []
    total_unrealized = 0
    total_market = 0
    total_basis = 0
    for r in holdings:
        h_id, ticker, name, price, flat_basis, shares, acct = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        lot_shares, lot_basis = float(r[7]), float(r[8])

        # Use lot data if available, else fall back to flat cost_basis
        if lot_shares > 0:
            basis = lot_basis
            qty = lot_shares
        else:
            qty = float(shares) if shares else 0
            basis = qty * float(flat_basis) if flat_basis and qty else 0

        market_val = qty * float(price) if price and qty else 0
        unrealized = market_val - basis if basis else None
        pct = ((unrealized / basis) * 100) if basis and basis != 0 and unrealized is not None else None

        total_market += market_val
        total_basis += basis
        if unrealized is not None:
            total_unrealized += unrealized

        items.append({
            "holding_id": h_id, "ticker": ticker, "name": name, "account": acct,
            "shares": float(qty), "price": float(price) if price else None,
            "market_value": round(market_val, 2),
            "cost_basis": round(basis, 2),
            "unrealized_gain": round(unrealized, 2) if unrealized is not None else None,
            "unrealized_pct": round(pct, 1) if pct is not None else None,
        })

    return {
        "holdings": items,
        "totals": {
            "market_value": round(total_market, 2),
            "cost_basis": round(total_basis, 2),
            "unrealized": round(total_unrealized, 2),
            "realized_total": float(realized[0]),
            "realized_long_term": float(realized[1]),
            "realized_short_term": float(realized[2]),
        },
    }
