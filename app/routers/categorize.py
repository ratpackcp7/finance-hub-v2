"""AI Categorization router — suggest + apply.

Privacy: Merchant names, descriptions, dates, and bucketed amounts are sent to
OpenRouter (Gemini Flash Lite). Exact dollar amounts are NOT sent.
Provenance: AI-applied categories tagged with category_source='ai'.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _audit, db_read, db_transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/categorize", tags=["categorize"])

OPENROUTER_KEY_FILE = Path("/run/secrets/openrouter_key")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-001"


def _get_openrouter_key() -> str:
    if OPENROUTER_KEY_FILE.exists():
        return OPENROUTER_KEY_FILE.read_text().strip()
    k = os.environ.get("OPENROUTER_API_KEY", "")
    if k:
        return k
    raise RuntimeError("OpenRouter key not found")


def _call_openrouter(prompt: str) -> str:
    key = _get_openrouter_key()
    req = urllib.request.Request(
        OPENROUTER_API_URL,
        data=json.dumps({"model": OPENROUTER_MODEL,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                 "HTTP-Referer": "https://cp7.dev", "X-Title": "Finance Hub"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenRouter error {e.code}: {e.read().decode()}")


def _bucket_amount(amount: float) -> str:
    amt = abs(amount)
    if amt < 10: return "under $10"
    elif amt < 25: return "$10-25"
    elif amt < 50: return "$25-50"
    elif amt < 100: return "$50-100"
    elif amt < 250: return "$100-250"
    elif amt < 500: return "$250-500"
    elif amt < 1000: return "$500-1K"
    else: return "over $1K"


def _build_ai_prompt(txns, categories):
    cl = "\n".join("  - " + c["name"] for c in sorted(categories, key=lambda x: x["name"]))
    ls = [f"  {i + 1}. [{t.get('posted', '')}] {t.get('payee') or t.get('description') or 'Unknown'} | "
          f"{_bucket_amount(t.get('amount', 0))}"
          f"{' (credit)' if t.get('amount', 0) > 0 else ''}" for i, t in enumerate(txns)]
    return (f"You are a personal finance categorizer.\n\nAVAILABLE CATEGORIES:\n{cl}\n\nTRANSACTIONS:\n"
            + "\n".join(ls)
            + '\n\nRules:\n- Match each to exactly one category.\n- If nothing fits, use "Uncategorized".\n'
              '- Return ONLY a JSON array.\n'
              '- Format: [{{"index": 1, "category": "Groceries", "confidence": "high"}}, ...]\n'
              '- Confidence: "high", "medium", "low"')


def _parse_ai_response(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.startswith("json") else raw
    return json.loads(raw.strip())


@router.get("/suggest")
def categorize_suggest(limit: int = 100):
    with db_read() as cur:
        # B.6: skip category_locked rows
        cur.execute(
            "SELECT t.id, t.posted, t.amount, t.description, t.payee FROM transactions t "
            "WHERE t.category_id IS NULL AND t.pending = FALSE "
            "AND t.category_manual = FALSE AND t.category_locked = FALSE "
            "ORDER BY t.posted DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        if not rows:
            return {"suggestions": [], "message": "No uncategorized transactions found"}
        txns = [{"id": r[0], "posted": r[1].isoformat() if r[1] else None,
                 "amount": float(r[2]) if r[2] else 0, "description": r[3], "payee": r[4]} for r in rows]
        cur.execute("SELECT id, name, color FROM categories WHERE deleted_at IS NULL ORDER BY name")
        categories = [{"id": r[0], "name": r[1], "color": r[2]} for r in cur.fetchall()]
        cur.execute(
            "SELECT match_pattern, category_id, c.name, payee_name "
            "FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id "
            "WHERE r.deleted_at IS NULL ORDER BY r.priority DESC, r.id")
        rules = [{"pattern": r[0], "category_id": r[1], "category": r[2], "payee_name": r[3]}
                 for r in cur.fetchall()]
    rule_results, unknowns = [], []
    for txn in txns:
        key = (txn.get("payee") or txn.get("description") or "").lower()
        matched = None
        for rule in rules:
            if rule["pattern"] and rule["pattern"] in key:
                matched = rule; break
        if matched:
            rule_results.append({"txn_id": txn["id"],
                                 "payee": txn.get("payee") or txn.get("description") or "Unknown",
                                 "posted": txn["posted"], "amount": txn["amount"],
                                 "category": matched["category"], "category_id": matched["category_id"],
                                 "confidence": "rule", "source": "rule"})
        else:
            unknowns.append(txn)
    ai_results = []
    if unknowns:
        try:
            parsed = _parse_ai_response(_call_openrouter(_build_ai_prompt(unknowns, categories)))
            cat_map = {c["name"]: c for c in categories}
            sugg_map = {s["index"]: s for s in parsed}
            for i, txn in enumerate(unknowns, 1):
                sugg = sugg_map.get(i, {})
                cn = sugg.get("category", "Uncategorized")
                co = cat_map.get(cn)
                ai_results.append({"txn_id": txn["id"],
                                   "payee": txn.get("payee") or txn.get("description") or "Unknown",
                                   "posted": txn["posted"], "amount": txn["amount"],
                                   "category": cn, "category_id": co["id"] if co else None,
                                   "confidence": sugg.get("confidence", "low"), "source": "ai"})
        except Exception as e:
            logger.error("AI categorization failed: %s", e)
            raise HTTPException(status_code=502, detail="AI error: " + str(e))
    return {"suggestions": rule_results + ai_results,
            "categories": [{"id": c["id"], "name": c["name"], "color": c["color"]} for c in categories],
            "stats": {"total": len(txns), "rule_matched": len(rule_results), "ai_suggested": len(ai_results)},
            "privacy_note": "Merchant names, descriptions, dates, and bucketed amounts are sent to the AI service (OpenRouter/Gemini). Exact dollar amounts are NOT sent."}


class CategorizeApplyItem(BaseModel):
    txn_id: str
    category_id: int
    make_rule: bool = False
    payee: Optional[str] = None
    source: str = "ai"


class CategorizeApplyRequest(BaseModel):
    items: list[CategorizeApplyItem]


@router.post("/apply")
def categorize_apply(body: CategorizeApplyRequest):
    with db_transaction() as cur:
        applied = rules_created = skipped_locked = 0
        for item in body.items:
            # B.6: check category_locked before overwriting
            cur.execute("SELECT category_id, category_source, category_locked FROM transactions WHERE id = %s", (item.txn_id,))
            old = cur.fetchone()
            if not old:
                continue
            if old[2]:  # category_locked = TRUE
                skipped_locked += 1
                continue
            source_tag = item.source if item.source in ("ai", "rule", "user") else "ai"
            is_manual = source_tag == "user"
            cur.execute(
                "UPDATE transactions SET category_id = %s, category_manual = %s, "
                "category_source = %s, updated_at = NOW() "
                "WHERE id = %s AND category_locked = FALSE", (item.category_id, is_manual, source_tag, item.txn_id))
            applied += 1
            _audit(cur, "transaction", item.txn_id, "categorize", source=source_tag,
                   field_name="category_id", old_value=old[0] if old else None, new_value=item.category_id)
            if item.make_rule and item.payee:
                pattern = item.payee.lower().strip()
                cur.execute("SELECT id FROM payee_rules WHERE match_pattern = %s AND deleted_at IS NULL",
                            (pattern,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority) "
                        "VALUES (%s, %s, %s, 0)", (pattern, item.payee, item.category_id))
                    rules_created += 1
    result = {"applied": applied, "rules_created": rules_created}
    if skipped_locked:
        result["skipped_locked"] = skipped_locked
    return result
