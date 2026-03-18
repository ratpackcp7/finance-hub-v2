"""Monthly digest router — generate + send spending summary to Telegram."""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import db_conn, db_put

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/digest", tags=["digest"])


def _get_month_range(month_str: Optional[str] = None):
    """Parse YYYY-MM or default to last complete month."""
    if month_str:
        yr, mo = int(month_str[:4]), int(month_str[5:7])
    else:
        today = date.today()
        first_of_this = date(today.year, today.month, 1)
        last_month_end = first_of_this - timedelta(days=1)
        yr, mo = last_month_end.year, last_month_end.month
    import calendar
    last_day = calendar.monthrange(yr, mo)[1]
    return date(yr, mo, 1), date(yr, mo, last_day), f"{yr}-{mo:02d}"


@router.get("/monthly")
def monthly_digest(month: Optional[str] = None):
    """Generate a monthly spending digest."""
    start, end, label = _get_month_range(month)
    conn = db_conn()
    try:
        cur = conn.cursor()

        # Income
        cur.execute(
            "SELECT SUM(t.amount) FROM transactions t "
            "LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount > 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.is_income, FALSE) = TRUE "
            "AND t.posted >= %s AND t.posted <= %s", (start, end))
        income = float(cur.fetchone()[0] or 0)

        # Spending
        cur.execute(
            "SELECT SUM(ABS(t.amount)) FROM spending_items t "
            "LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s", (start, end))
        spending = float(cur.fetchone()[0] or 0)

        net = income - spending

        # Top 5 spending categories
        cur.execute(
            "SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount)) "
            "FROM spending_items t LEFT JOIN categories c ON t.category_id = c.id "
            "WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE "
            "AND COALESCE(c.name, '') NOT IN ('Credit Card Pay', 'Transfer') "
            "AND t.posted >= %s AND t.posted <= %s "
            "GROUP BY c.name ORDER BY 2 DESC LIMIT 5", (start, end))
        top_categories = [{"category": r[0], "amount": float(r[1])} for r in cur.fetchall()]

        # Budget status
        cur.execute(
            "SELECT c.name, b.monthly_amount, "
            "COALESCE((SELECT SUM(ABS(si.amount)) FROM spending_items si "
            "  LEFT JOIN categories sc ON si.category_id = sc.id "
            "  WHERE si.amount < 0 AND si.pending = FALSE AND si.is_transfer = FALSE "
            "  AND si.category_id = b.category_id "
            "  AND si.posted >= %s AND si.posted <= %s), 0) "
            "FROM budgets b JOIN categories c ON b.category_id = c.id "
            "WHERE b.deleted_at IS NULL", (start, end))
        budget_items = []
        over_budget = 0
        for name, budget_amt, actual in cur.fetchall():
            ba = float(budget_amt)
            ac = float(actual)
            over = ac > ba
            if over:
                over_budget += 1
            budget_items.append({"category": name, "budget": ba, "actual": ac, "over": over})

        # Net worth (latest snapshot in the period)
        cur.execute(
            "SELECT snapshot_date, SUM(balance) FROM balance_snapshots "
            "WHERE snapshot_date <= %s GROUP BY snapshot_date "
            "ORDER BY snapshot_date DESC LIMIT 1", (end,))
        nw_end = cur.fetchone()
        cur.execute(
            "SELECT snapshot_date, SUM(balance) FROM balance_snapshots "
            "WHERE snapshot_date < %s GROUP BY snapshot_date "
            "ORDER BY snapshot_date DESC LIMIT 1", (start,))
        nw_start = cur.fetchone()

        nw_current = float(nw_end[1]) if nw_end else None
        nw_previous = float(nw_start[1]) if nw_start else None
        nw_change = (nw_current - nw_previous) if nw_current is not None and nw_previous is not None else None

        # Upcoming bills count (next 30 days from end of period)
        cur.execute(
            "SELECT COUNT(DISTINCT COALESCE(t.payee, t.description)) "
            "FROM transactions t WHERE t.recurring = TRUE AND t.pending = FALSE "
            "AND t.posted >= %s", (end - timedelta(days=60),))
        upcoming_bills = cur.fetchone()[0] or 0

        # Savings rate
        savings_rate = ((income - spending) / income * 100) if income > 0 else 0

    finally:
        db_put(conn)

    return {
        "month": label,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "income": round(income, 2),
        "spending": round(spending, 2),
        "net": round(net, 2),
        "savings_rate": round(savings_rate, 1),
        "top_categories": top_categories,
        "budget_summary": {
            "items": budget_items,
            "over_budget_count": over_budget,
            "total_budgets": len(budget_items),
        },
        "net_worth": {
            "current": round(nw_current, 2) if nw_current else None,
            "previous": round(nw_previous, 2) if nw_previous else None,
            "change": round(nw_change, 2) if nw_change else None,
        },
        "upcoming_recurring_bills": upcoming_bills,
    }


def _format_digest_text(data: dict) -> str:
    """Format digest as a Telegram-friendly message."""
    m = data["month"]
    lines = [
        f"💰 *Finance Hub — {m} Digest*",
        "",
        f"📊 *Summary*",
        f"  Income: ${data['income']:,.2f}",
        f"  Spending: ${data['spending']:,.2f}",
        f"  Net: {'✅' if data['net'] >= 0 else '🔴'} ${data['net']:,.2f}",
        f"  Savings rate: {data['savings_rate']:.1f}%",
    ]

    if data["top_categories"]:
        lines += ["", "🏷 *Top Spending*"]
        for i, c in enumerate(data["top_categories"], 1):
            lines.append(f"  {i}. {c['category']}: ${c['amount']:,.2f}")

    bs = data["budget_summary"]
    if bs["total_budgets"]:
        over = [b for b in bs["items"] if b["over"]]
        if over:
            lines += ["", f"⚠️ *Over Budget ({len(over)})*"]
            for b in over[:5]:
                lines.append(f"  {b['category']}: ${b['actual']:,.2f} / ${b['budget']:,.2f}")
        else:
            lines.append(f"\n✅ All {bs['total_budgets']} budgets on track")

    nw = data["net_worth"]
    if nw["current"] is not None:
        arrow = "📈" if (nw["change"] or 0) >= 0 else "📉"
        lines += ["", f"{arrow} *Net Worth*"]
        lines.append(f"  ${nw['current']:,.2f}")
        if nw["change"] is not None:
            lines.append(f"  Change: {'+'if nw['change']>=0 else ''}{nw['change']:,.2f}")

    lines += ["", f"📅 {data['upcoming_recurring_bills']} recurring bills tracked"]
    lines += ["", "_Generated by Finance Hub_"]

    return "\n".join(lines)


class TelegramSendRequest(BaseModel):
    month: Optional[str] = None
    chat_id: Optional[str] = None


@router.post("/send-telegram")
def send_telegram_digest(body: TelegramSendRequest = TelegramSendRequest()):
    """Generate and send monthly digest to Telegram."""
    import os
    from pathlib import Path

    # Get bot token
    token_path = Path("/run/secrets/telegram_bot_token")
    if token_path.exists():
        bot_token = token_path.read_text().strip()
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram bot token not configured")

    chat_id = body.chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id required (or set TELEGRAM_CHAT_ID env var)")

    # Generate digest
    data = monthly_digest(body.month)
    text = _format_digest_text(data)

    # Send to Telegram
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            })
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                raise HTTPException(status_code=500, detail=f"Telegram API error: {result}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Telegram send failed: {e}")

    logger.info("Digest sent to Telegram chat %s for %s", chat_id, data["month"])
    return {"status": "ok", "month": data["month"], "chat_id": chat_id}
