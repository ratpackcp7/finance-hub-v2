"""Monthly digest router — generate + send spending summary to Telegram."""
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import db_read
from shared.summary import get_month_range, monthly_spending_summary, net_worth_at

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/digest", tags=["digest"])


def _read_telegram_chat_id() -> str:
    """C.8: Read chat ID from Docker secret, fall back to env."""
    p = Path("/run/secrets/telegram_chat_id")
    if p.exists():
        return p.read_text().strip()
    val = os.environ.get("TELEGRAM_CHAT_ID")
    if val:
        return val
    raise RuntimeError("TELEGRAM_CHAT_ID not configured (secret or env)")


@router.get("/monthly")
def monthly_digest(month: Optional[str] = None):
    """Generate a monthly spending digest."""
    start, end, label = get_month_range(month)
    with db_read() as cur:

        # C.7: Use shared spending summary helper
        summary = monthly_spending_summary(cur, start, end)

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

        # C.7: Use shared net worth helper
        nw_current = net_worth_at(cur, end)
        nw_previous = net_worth_at(cur, start - timedelta(days=1))
        nw_change = (nw_current - nw_previous) if nw_current is not None and nw_previous is not None else None

        # Upcoming bills count (next 30 days from end of period)
        cur.execute(
            "SELECT COUNT(DISTINCT COALESCE(t.payee, t.description)) "
            "FROM transactions t WHERE t.recurring = TRUE AND t.pending = FALSE "
            "AND t.posted >= %s", (end - timedelta(days=60),))
        upcoming_bills = cur.fetchone()[0] or 0

    return {
        "month": label,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "income": summary["income"],
        "spending": summary["spending"],
        "net": summary["net"],
        "savings_rate": summary["savings_rate"],
        "top_categories": summary["top_categories"],
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
        f"\U0001f4b0 *Finance Hub \u2014 {m} Digest*",
        "",
        f"\U0001f4ca *Summary*",
        f"  Income: ${data['income']:,.2f}",
        f"  Spending: ${data['spending']:,.2f}",
        f"  Net: {'\u2705' if data['net'] >= 0 else '\U0001f534'} ${data['net']:,.2f}",
        f"  Savings rate: {data['savings_rate']:.1f}%",
    ]

    if data["top_categories"]:
        lines += ["", "\U0001f3f7 *Top Spending*"]
        for i, c in enumerate(data["top_categories"], 1):
            lines.append(f"  {i}. {c['category']}: ${c['amount']:,.2f}")

    bs = data["budget_summary"]
    if bs["total_budgets"]:
        over = [b for b in bs["items"] if b["over"]]
        if over:
            lines += ["", f"\u26a0\ufe0f *Over Budget ({len(over)})*"]
            for b in over[:5]:
                lines.append(f"  {b['category']}: ${b['actual']:,.2f} / ${b['budget']:,.2f}")
        else:
            lines.append(f"\n\u2705 All {bs['total_budgets']} budgets on track")

    nw = data["net_worth"]
    if nw["current"] is not None:
        arrow = "\U0001f4c8" if (nw["change"] or 0) >= 0 else "\U0001f4c9"
        lines += ["", f"{arrow} *Net Worth*"]
        lines.append(f"  ${nw['current']:,.2f}")
        if nw["change"] is not None:
            lines.append(f"  Change: {'+'if nw['change']>=0 else ''}{nw['change']:,.2f}")

    lines += ["", f"\U0001f4c5 {data['upcoming_recurring_bills']} recurring bills tracked"]
    lines += ["", "_Generated by Finance Hub_"]

    return "\n".join(lines)


class TelegramSendRequest(BaseModel):
    month: Optional[str] = None
    chat_id: Optional[str] = None


@router.post("/send-telegram")
def send_telegram_digest(body: TelegramSendRequest = TelegramSendRequest()):
    """Generate and send monthly digest to Telegram."""
    # Get bot token
    token_path = Path("/run/secrets/telegram_bot_token")
    if token_path.exists():
        bot_token = token_path.read_text().strip()
    else:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram bot token not configured")

    # C.8: Read chat ID from secret
    chat_id = body.chat_id or _read_telegram_chat_id()

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
