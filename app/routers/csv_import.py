"""CSV Import router — upload, preview, apply, mappings CRUD.

Supports auto-detection of known bank CSV formats (Chase, Discover, Citi)
via header matching against saved csv_mappings presets.
"""
import csv
import hashlib
import io
import json
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from db import _audit, db_read, db_transaction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/csv-import", tags=["csv-import"])

# ── Date parsing ──

DATE_FORMATS = [
    "%m/%d/%Y",   # 01/15/2026
    "%m/%d/%y",   # 01/15/26
    "%Y-%m-%d",   # 2026-01-15
    "%m-%d-%Y",   # 01-15-2026
    "%d/%m/%Y",   # 15/01/2026 (EU)
]


def _parse_date(val: str) -> Optional[date]:
    val = val.strip()
    if not val:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(val: str) -> Optional[float]:
    if not val or not val.strip():
        return None
    cleaned = val.strip().replace("$", "").replace(",", "")
    # Handle parentheses as negative: (123.45) -> -123.45
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── Header matching ──

def _normalize_headers(headers: list[str]) -> str:
    return ",".join(h.strip().lower() for h in headers)


def _detect_mapping(headers: list[str], cur) -> Optional[dict]:
    """Try to match CSV headers against known csv_mappings presets."""
    sig = _normalize_headers(headers)
    cur.execute(
        "SELECT id, name, institution, header_signature, mapping, sign_flip, date_format, notes "
        "FROM csv_mappings ORDER BY is_preset DESC, id")
    for row in cur.fetchall():
        preset_sig = row[3]
        if preset_sig == sig:
            mapping = row[4] if isinstance(row[4], dict) else json.loads(row[4])
            return {
                "mapping_id": row[0],
                "name": row[1],
                "institution": row[2],
                "mapping": mapping,
                "sign_flip": row[5],
                "date_format": row[6],
                "notes": row[7],
            }
    return None


# ── Preview endpoint ──

@router.post("/preview")
async def csv_preview(file: UploadFile = File(...), account_id: str = Form(...)):
    """Upload a CSV, auto-detect format, return preview rows + detected mapping."""
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="CSV must have a header row and at least one data row")

    headers = [h.strip() for h in rows[0]]

    # Auto-detect mapping
    with db_read() as cur:
        detected = _detect_mapping(headers, cur)

        # Verify account exists
        cur.execute("SELECT id, name FROM accounts WHERE id = %s", (account_id,))
        acct = cur.fetchone()
        if not acct:
            raise HTTPException(status_code=400, detail=f"Account not found: {account_id}")
        account_name = acct[1]

    # Parse preview rows
    preview = []
    data_rows = rows[1:]
    mapping = detected["mapping"] if detected else None

    for i, row in enumerate(data_rows[:20]):  # preview first 20
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))
        row_dict = dict(zip(headers, row))

        parsed = {"_row": i + 1, "_raw": row_dict}
        if mapping:
            # Extract date
            date_col = mapping.get("date_col")
            parsed["date"] = row_dict.get(date_col, "") if date_col else ""
            parsed["date_parsed"] = _parse_date(parsed["date"]).isoformat() if _parse_date(parsed["date"]) else None

            # Extract description
            desc_col = mapping.get("description_col")
            parsed["description"] = row_dict.get(desc_col, "") if desc_col else ""

            # Extract amount (single column or dual debit/credit)
            amount_col = mapping.get("amount_col")
            debit_col = mapping.get("debit_col")
            credit_col = mapping.get("credit_col")

            if amount_col:
                amt = _parse_amount(row_dict.get(amount_col, ""))
                if amt is not None and detected and detected.get("sign_flip"):
                    amt = -amt
                parsed["amount"] = amt
            elif debit_col and credit_col:
                debit = _parse_amount(row_dict.get(debit_col, ""))
                credit = _parse_amount(row_dict.get(credit_col, ""))
                if debit:
                    parsed["amount"] = -abs(debit)
                elif credit:
                    parsed["amount"] = abs(credit)
                else:
                    parsed["amount"] = None
            else:
                parsed["amount"] = None

            # Optional: category from CSV
            cat_col = mapping.get("category_col")
            parsed["csv_category"] = row_dict.get(cat_col, "") if cat_col else ""

        preview.append(parsed)

    return {
        "file_name": file.filename,
        "account_id": account_id,
        "account_name": account_name,
        "headers": headers,
        "total_rows": len(data_rows),
        "detected_mapping": detected,
        "preview": preview,
    }


# ── Apply import ──

class CsvApplyRequest(BaseModel):
    account_id: str
    mapping_id: Optional[int] = None
    # Manual mapping override (if no preset detected)
    date_col: Optional[str] = None
    description_col: Optional[str] = None
    amount_col: Optional[str] = None
    debit_col: Optional[str] = None
    credit_col: Optional[str] = None
    sign_flip: bool = False


def _fail_batch(batch_id: Optional[int], error_msg: str):
    """Mark an import batch as failed using a separate transaction.

    Uses its own connection because the caller's transaction will be rolled back.
    """
    if batch_id is None:
        return
    try:
        with db_transaction() as cur:
            cur.execute(
                "UPDATE import_batches SET status='error', finished_at=NOW(), error_message=%s WHERE id=%s",
                (error_msg, batch_id))
    except Exception:
        pass


@router.post("/apply")
async def csv_apply(file: UploadFile = File(...), config: str = Form(...)):
    """Import CSV transactions. Config is JSON-encoded CsvApplyRequest."""
    try:
        cfg = json.loads(config)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="config must be valid JSON")

    account_id = cfg.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="CSV must have header + data rows")

    headers = [h.strip() for h in rows[0]]
    data_rows = rows[1:]

    batch_id = None
    try:
      with db_transaction() as cur:
        categorized = 0

        # Verify account
        cur.execute("SELECT id FROM accounts WHERE id = %s", (account_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Account not found: {account_id}")

        # Resolve mapping
        mapping_id = cfg.get("mapping_id")
        sign_flip = cfg.get("sign_flip", False)
        mapping = {}

        if mapping_id:
            cur.execute("SELECT mapping, sign_flip FROM csv_mappings WHERE id = %s", (mapping_id,))
            row = cur.fetchone()
            if row:
                mapping = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                sign_flip = row[1]
        else:
            # Manual mapping from config
            for key in ("date_col", "description_col", "amount_col", "debit_col", "credit_col"):
                if cfg.get(key):
                    mapping[key] = cfg[key]

        if not mapping.get("date_col"):
            raise HTTPException(status_code=400, detail="No date column mapped")
        if not mapping.get("amount_col") and not (mapping.get("debit_col") and mapping.get("credit_col")):
            raise HTTPException(status_code=400, detail="No amount column(s) mapped")

        # Create import batch
        cur.execute(
            "INSERT INTO import_batches (status, source) VALUES ('running', 'csv') RETURNING id")
        batch_id = cur.fetchone()[0]

        added = skipped = dupes = errors = 0

        for i, row in enumerate(data_rows):
            if len(row) < len(headers):
                row += [""] * (len(headers) - len(row))
            row_dict = dict(zip(headers, row))

            # Parse date
            date_val = _parse_date(row_dict.get(mapping["date_col"], ""))
            if not date_val:
                errors += 1
                continue

            # Parse description
            desc_col = mapping.get("description_col")
            description = row_dict.get(desc_col, "").strip() if desc_col else ""
            if not description:
                errors += 1
                continue

            # Parse amount
            amount = None
            amount_col = mapping.get("amount_col")
            debit_col = mapping.get("debit_col")
            credit_col = mapping.get("credit_col")

            if amount_col:
                amount = _parse_amount(row_dict.get(amount_col, ""))
                if amount is not None and sign_flip:
                    amount = -amount
            elif debit_col and credit_col:
                debit = _parse_amount(row_dict.get(debit_col, ""))
                credit = _parse_amount(row_dict.get(credit_col, ""))
                if debit:
                    amount = -abs(debit)
                elif credit:
                    amount = abs(credit)

            if amount is None:
                errors += 1
                continue

            # Dedup: same account + date + amount + description
            cur.execute(
                "SELECT id FROM transactions WHERE account_id = %s AND posted = %s "
                "AND ABS(amount - %s) < 0.01 AND description = %s LIMIT 1",
                (account_id, date_val, amount, description))
            if cur.fetchone():
                dupes += 1  # C.5: count duplicates
                skipped += 1
                continue

            # Generate content-based deterministic ID (no row index — order-independent)
            txn_id = "csv_" + hashlib.sha256(
                f"{account_id}:{date_val}:{amount:.2f}:{description}".encode()
            ).hexdigest()[:24]

            # Check if this generated ID already exists
            cur.execute("SELECT id FROM transactions WHERE id = %s", (txn_id,))
            if cur.fetchone():
                skipped += 1
                continue

            cur.execute(
                "INSERT INTO transactions (id, account_id, posted, amount, description, "
                "pending, import_batch_id, first_import_batch_id, last_seen_batch_id, category_source) "
                "VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s, %s, NULL)",
                (txn_id, account_id, date_val, amount, description, batch_id, batch_id, batch_id))
            added += 1

            _audit(cur, "transaction", txn_id, "csv_import", source="csv",
                   field_name="import_batch_id", new_value=batch_id)

        # Apply payee rules to new transactions
        from syncer import apply_payee_rules
        categorized = apply_payee_rules(cur)

        # Close batch
        cur.execute(
            "UPDATE import_batches SET status='ok', finished_at=NOW(), "
            "source='csv', accounts_seen=1, txns_added=%s, txns_skipped=%s, "
            "dupes_flagged=%s, error_message=%s WHERE id=%s",
            (added, skipped, dupes,
             f"{errors} rows had parse errors" if errors else None,
             batch_id))

    except HTTPException as he:
        _fail_batch(batch_id, str(he.detail))
        raise
    except Exception as e:
        _fail_batch(batch_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "ok",
        "batch_id": batch_id,
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "auto_categorized": categorized,
        "file_name": file.filename,
    }


# ── Mappings CRUD ──

@router.get("/mappings")
def list_mappings():
    with db_read() as cur:
        cur.execute(
            "SELECT id, name, institution, header_signature, mapping, sign_flip, "
            "date_format, notes, is_preset, created_at "
            "FROM csv_mappings ORDER BY is_preset DESC, name")
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "institution": r[2],
             "header_signature": r[3],
             "mapping": r[4] if isinstance(r[4], dict) else json.loads(r[4]),
             "sign_flip": r[5], "date_format": r[6], "notes": r[7],
             "is_preset": r[8],
             "created_at": r[9].isoformat() if r[9] else None} for r in rows]


class MappingCreate(BaseModel):
    name: str
    institution: Optional[str] = None
    header_signature: str
    mapping: dict
    sign_flip: bool = False
    date_format: str = "MM/DD/YYYY"
    notes: Optional[str] = None


@router.post("/mappings")
def create_mapping(body: MappingCreate):
    with db_transaction() as cur:
        cur.execute(
            "INSERT INTO csv_mappings (name, institution, header_signature, mapping, "
            "sign_flip, date_format, notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (body.name, body.institution, body.header_signature,
             json.dumps(body.mapping), body.sign_flip, body.date_format, body.notes))
        new_id = cur.fetchone()[0]
    return {"id": new_id, "name": body.name}


@router.delete("/mappings/{mapping_id}")
def delete_mapping(mapping_id: int):
    with db_transaction() as cur:
        cur.execute("SELECT is_preset FROM csv_mappings WHERE id = %s", (mapping_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Mapping not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot delete built-in presets")
        cur.execute("DELETE FROM csv_mappings WHERE id = %s", (mapping_id,))
    return {"status": "ok"}
