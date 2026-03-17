"""
Finance Hub v2 — FastAPI application
"""
import csv
import io
import json
import logging
import os
import urllib.error
import urllib.request
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.pool
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from syncer import run_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

def read_secret(name: str) -> str:
    p = Path(f"/run/secrets/{name}")
    if p.exists(): return p.read_text().strip()
    val = os.environ.get(name.upper())
    if val: return val
    raise RuntimeError(f"Secret '{name}' not found")

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)), dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"], password=read_secret("db_password"))
    return _pool

def db_conn(): return get_pool().getconn()
def db_put(conn): get_pool().putconn(conn)

def run_migrations():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_transfer BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_transfer ON transactions(is_transfer) WHERE is_transfer = TRUE")
        cur.execute("""CREATE TABLE IF NOT EXISTS budgets (
            id SERIAL PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            monthly_amount NUMERIC(15,2) NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(category_id))""")
        cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS account_type TEXT DEFAULT 'checking'")
        cur.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY, type TEXT NOT NULL DEFAULT 'feature',
            message TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW(),
            notion_page_id TEXT DEFAULT NULL)""")
        conn.commit(); logger.info("Migrations complete")
    except Exception as e: conn.rollback(); logger.error("Migration failed: %s", e)
    finally: db_put(conn)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = db_conn(); db_put(conn); logger.info("DB pool ready"); run_migrations()
    except Exception as e: logger.error("DB pool init failed: %s", e)
    yield
    if _pool: _pool.closeall()

app = FastAPI(title="Finance Hub", version="3.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index(): return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/health")
def health(): return {"status": "ok", "ts": datetime.utcnow().isoformat()}

# ── Sync ──
_sync_running = False

def _do_sync(start_date: Optional[date] = None):
    global _sync_running
    _sync_running = True
    conn = db_conn()
    try: run_sync(conn, start_date)
    except Exception as e: logger.error("Manual sync failed: %s", e)
    finally: db_put(conn); _sync_running = False

class SyncRequest(BaseModel):
    start_date: Optional[date] = None

@app.post("/api/sync")
def trigger_sync(body: SyncRequest, background_tasks: BackgroundTasks):
    if _sync_running: raise HTTPException(status_code=409, detail="Sync already in progress")
    background_tasks.add_task(_do_sync, body.start_date); return {"status": "started"}

@app.get("/api/sync/status")
def sync_status(): return {"running": _sync_running}

@app.get("/api/sync/log")
def sync_log(limit: int = 20):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, started_at, finished_at, status, accounts_seen, txns_added, txns_updated, error_message FROM sync_log ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "started_at": r[1].isoformat() if r[1] else None, "finished_at": r[2].isoformat() if r[2] else None, "status": r[3], "accounts_seen": r[4], "txns_added": r[5], "txns_updated": r[6], "error_message": r[7]} for r in rows]

# ── Accounts ──
ACCOUNT_TYPES = {"checking", "savings", "credit", "investment", "retirement", "529", "utma", "hsa", "brokerage", "loan", "mortgage", "other"}

@app.get("/api/accounts")
def get_accounts():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, org_name, currency, balance, balance_date, on_budget, hidden, updated_at, account_type FROM accounts WHERE hidden = FALSE ORDER BY org_name, name")
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "name": r[1], "org": r[2], "currency": r[3], "balance": float(r[4]) if r[4] is not None else None, "balance_date": r[5].isoformat() if r[5] else None, "on_budget": r[6], "hidden": r[7], "updated_at": r[8].isoformat() if r[8] else None, "account_type": r[9] or "checking"} for r in rows]

class AccountPatch(BaseModel):
    account_type: Optional[str] = None

@app.patch("/api/accounts/{acct_id}")
def patch_account(acct_id: str, body: AccountPatch):
    if body.account_type and body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail=f"account_type must be one of: {', '.join(sorted(ACCOUNT_TYPES))}")
    conn = db_conn()
    try:
        cur = conn.cursor()
        if body.account_type is not None:
            cur.execute("UPDATE accounts SET account_type = %s, updated_at = NOW() WHERE id = %s", (body.account_type, acct_id))
            conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

@app.get("/api/accounts/net-worth")
def net_worth():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(account_type, 'checking'), SUM(balance), COUNT(*) FROM accounts WHERE hidden = FALSE AND balance IS NOT NULL GROUP BY 1 ORDER BY 1")
        rows = cur.fetchall()
    finally: db_put(conn)
    groups = [{"type": r[0], "total": float(r[1]), "count": r[2]} for r in rows]
    return {"groups": groups, "net_worth": sum(g["total"] for g in groups)}

# ── Transactions ──
def _txn_filters(account_id=None, category_id=None, start_date=None, end_date=None, search=None, pending=None, exclude_transfers=False):
    filters, params = [], []
    if account_id: filters.append("t.account_id = %s"); params.append(account_id)
    if category_id is not None: filters.append("t.category_id = %s"); params.append(category_id)
    if start_date: filters.append("t.posted >= %s"); params.append(start_date)
    if end_date: filters.append("t.posted <= %s"); params.append(end_date)
    if search:
        filters.append("(lower(t.description) LIKE %s OR lower(t.payee) LIKE %s)")
        params += [f"%{search.lower()}%", f"%{search.lower()}%"]
    if pending is not None: filters.append("t.pending = %s"); params.append(pending)
    if exclude_transfers: filters.append("t.is_transfer = FALSE")
    return filters, params

@app.get("/api/transactions")
def get_transactions(limit: int = 200, offset: int = 0, account_id: Optional[str] = None, category_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, search: Optional[str] = None, pending: Optional[bool] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = _txn_filters(account_id, category_id, start_date, end_date, search, pending)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(f"SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee, t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer FROM transactions t JOIN accounts a ON t.account_id = a.id LEFT JOIN categories c ON t.category_id = c.id {where} ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s", params + [limit, offset])
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM transactions t {where}", params)
        total = cur.fetchone()[0]
    finally: db_put(conn)
    return {"total": total, "limit": limit, "offset": offset, "transactions": [{"id": r[0], "account_id": r[1], "account_name": r[2], "posted": r[3].isoformat() if r[3] else None, "amount": float(r[4]) if r[4] is not None else None, "description": r[5], "payee": r[6], "category_id": r[7], "category": r[8], "category_manual": r[9], "pending": r[10], "notes": r[11], "is_transfer": r[12]} for r in rows]}

@app.get("/api/transactions/export")
def export_transactions(account_id: Optional[str] = None, category_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, search: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = _txn_filters(account_id, category_id, start_date, end_date, search)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        cur.execute(f"SELECT t.posted, COALESCE(t.payee, t.description, ''), t.description, a.name, COALESCE(c.name, 'Uncategorized'), t.amount, t.is_transfer, t.notes FROM transactions t JOIN accounts a ON t.account_id = a.id LEFT JOIN categories c ON t.category_id = c.id {where} ORDER BY t.posted DESC, t.id", params)
        rows = cur.fetchall()
    finally: db_put(conn)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Payee", "Description", "Account", "Category", "Amount", "Transfer", "Notes"])
    for r in rows: w.writerow([r[0].isoformat() if r[0] else "", r[1], r[2], r[3], r[4], f"{float(r[5]):.2f}" if r[5] is not None else "", "Yes" if r[6] else "", r[7] or ""])
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="finance_hub_{date.today().isoformat()}.csv"'})

class TxnPatch(BaseModel):
    category_id: Optional[int] = None
    payee: Optional[str] = None
    notes: Optional[str] = None

@app.patch("/api/transactions/{txn_id}")
def patch_transaction(txn_id: str, body: TxnPatch):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM transactions WHERE id = %s", (txn_id,))
        if not cur.fetchone(): raise HTTPException(status_code=404, detail="Transaction not found")
        updates, params = [], []
        if body.category_id is not None: updates += ["category_id = %s", "category_manual = TRUE"]; params.append(body.category_id)
        if body.payee is not None: updates.append("payee = %s"); params.append(body.payee)
        if body.notes is not None: updates.append("notes = %s"); params.append(body.notes)
        if not updates: return {"status": "no-op"}
        updates.append("updated_at = NOW()"); params.append(txn_id)
        cur.execute(f"UPDATE transactions SET {', '.join(updates)} WHERE id = %s", params); conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

# ── Transfer Detection ──
@app.patch("/api/transactions/{txn_id}/transfer")
def toggle_transfer(txn_id: str):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE transactions SET is_transfer = NOT is_transfer, updated_at = NOW() WHERE id = %s RETURNING is_transfer", (txn_id,))
        row = cur.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Transaction not found")
        conn.commit()
    finally: db_put(conn)
    return {"status": "ok", "is_transfer": row[0]}

@app.post("/api/transfers/detect")
def detect_transfers(days_window: int = 3, amount_tolerance: float = 0.01):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT t1.id, t1.account_id, a1.name, t1.posted, t1.amount, t1.description, t2.id, t2.account_id, a2.name, t2.posted, t2.amount, t2.description FROM transactions t1 JOIN transactions t2 ON t1.id < t2.id JOIN accounts a1 ON t1.account_id = a1.id JOIN accounts a2 ON t2.account_id = a2.id WHERE t1.account_id != t2.account_id AND t1.is_transfer = FALSE AND t2.is_transfer = FALSE AND t1.pending = FALSE AND t2.pending = FALSE AND ABS(t1.amount + t2.amount) <= %s AND ABS(t1.posted - t2.posted) <= %s ORDER BY t1.posted DESC LIMIT 200""", (amount_tolerance, days_window))
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"txn1": {"id": r[0], "account_id": r[1], "account_name": r[2], "posted": r[3].isoformat() if r[3] else None, "amount": float(r[4]), "description": r[5]}, "txn2": {"id": r[6], "account_id": r[7], "account_name": r[8], "posted": r[9].isoformat() if r[9] else None, "amount": float(r[10]), "description": r[11]}} for r in rows]

class TransferApplyRequest(BaseModel):
    pairs: list[list[str]]

@app.post("/api/transfers/apply")
def apply_transfers(body: TransferApplyRequest):
    conn = db_conn(); marked = 0
    try:
        cur = conn.cursor()
        for pair in body.pairs:
            for txn_id in pair: cur.execute("UPDATE transactions SET is_transfer = TRUE, updated_at = NOW() WHERE id = %s", (txn_id,)); marked += 1
        conn.commit()
    finally: db_put(conn)
    return {"marked": marked}

# ── Categories ──
@app.get("/api/categories")
def get_categories():
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT id, name, color, group_name, is_income, sort_order FROM categories ORDER BY sort_order, name"); rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "name": r[1], "color": r[2], "group": r[3], "is_income": r[4], "sort_order": r[5]} for r in rows]

class CategoryCreate(BaseModel):
    name: str; color: str = "#64748b"; group_name: Optional[str] = None; is_income: bool = False

@app.post("/api/categories", status_code=201)
def create_category(body: CategoryCreate):
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("INSERT INTO categories (name, color, group_name, is_income) VALUES (%s, %s, %s, %s) RETURNING id", (body.name, body.color, body.group_name, body.is_income))
        new_id = cur.fetchone()[0]; conn.commit()
    finally: db_put(conn)
    return {"id": new_id, "name": body.name}

@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT name FROM categories WHERE id = %s", (cat_id,)); row = cur.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Category not found")
        if row[0] == "Uncategorized": raise HTTPException(status_code=400, detail="Cannot delete Uncategorized")
        cur.execute("UPDATE transactions SET category_id = NULL WHERE category_id = %s", (cat_id,))
        cur.execute("DELETE FROM payee_rules WHERE category_id = %s", (cat_id,))
        cur.execute("DELETE FROM budgets WHERE category_id = %s", (cat_id,))
        cur.execute("DELETE FROM categories WHERE id = %s", (cat_id,)); conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

class CategoryRename(BaseModel):
    name: str

@app.patch("/api/categories/{cat_id}")
def rename_category(cat_id: int, body: CategoryRename):
    name = body.name.strip()
    if not name: raise HTTPException(status_code=400, detail="Name required")
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT name FROM categories WHERE id = %s", (cat_id,)); row = cur.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Category not found")
        if row[0] == "Uncategorized": raise HTTPException(status_code=400, detail="Cannot rename Uncategorized")
        cur.execute("UPDATE categories SET name = %s WHERE id = %s", (name, cat_id)); conn.commit()
    finally: db_put(conn)
    return {"status": "ok", "name": name}

# ── Payee Rules ──
@app.get("/api/payee-rules")
def get_payee_rules():
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT r.id, r.match_pattern, r.payee_name, r.category_id, c.name, r.priority FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id ORDER BY r.priority DESC, r.id"); rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "pattern": r[1], "payee_name": r[2], "category_id": r[3], "category": r[4], "priority": r[5]} for r in rows]

class PayeeRuleCreate(BaseModel):
    match_pattern: str; payee_name: Optional[str] = None; category_id: Optional[int] = None; priority: int = 0

@app.post("/api/payee-rules", status_code=201)
def create_payee_rule(body: PayeeRuleCreate):
    conn = db_conn()
    try:
        cur = conn.cursor()
        pattern = body.match_pattern.lower().strip()
        # Dedup: skip if exact pattern already exists
        cur.execute("SELECT id FROM payee_rules WHERE match_pattern = %s", (pattern,))
        existing = cur.fetchone()
        if existing:
            # Update category if different
            cur.execute("UPDATE payee_rules SET category_id = COALESCE(%s, category_id), payee_name = COALESCE(%s, payee_name) WHERE id = %s", (body.category_id, body.payee_name, existing[0]))
            new_id = existing[0]
        else:
            cur.execute("INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority) VALUES (%s, %s, %s, %s) RETURNING id", (pattern, body.payee_name, body.category_id, body.priority))
            new_id = cur.fetchone()[0]
        # Retroactively apply this rule to existing uncategorized transactions
        search_pattern = pattern
        cur.execute("""UPDATE transactions SET category_id = %s, payee = COALESCE(%s, payee), updated_at = NOW()
            WHERE category_id IS NULL AND category_manual = FALSE
            AND (lower(description) LIKE %s OR lower(COALESCE(payee,'')) LIKE %s)""",
            (body.category_id, body.payee_name, f"%{search_pattern}%", f"%{search_pattern}%"))
        retro = cur.rowcount
        conn.commit()
        logger.info("Rule %s (pattern=%s): retroactively categorized %d transactions", new_id, pattern, retro)
    finally: db_put(conn)
    return {"id": new_id, "retroactive": retro}

@app.delete("/api/payee-rules/{rule_id}")
def delete_payee_rule(rule_id: int):
    conn = db_conn()
    try: cur = conn.cursor(); cur.execute("DELETE FROM payee_rules WHERE id = %s", (rule_id,)); conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

# ── Spending Analytics ──
@app.get("/api/spending/by-category")
def spending_by_category(start_date: Optional[date] = None, end_date: Optional[date] = None, account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor(); f = ["t.amount < 0", "t.pending = FALSE", "t.is_transfer = FALSE"]; p = []
        if start_date: f.append("t.posted >= %s"); p.append(start_date)
        if end_date: f.append("t.posted <= %s"); p.append(end_date)
        if account_id: f.append("t.account_id = %s"); p.append(account_id)
        cur.execute(f"SELECT COALESCE(c.name, 'Uncategorized'), c.color, c.group_name, SUM(ABS(t.amount)), COUNT(*) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE {' AND '.join(f)} GROUP BY c.name, c.color, c.group_name ORDER BY 4 DESC", p)
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"category": r[0], "color": r[1] or "#475569", "group": r[2], "total": float(r[3]), "count": r[4]} for r in rows]

@app.get("/api/spending/by-payee")
def spending_by_payee(start_date: Optional[date] = None, end_date: Optional[date] = None, limit: int = 25, account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor(); f = ["amount < 0", "pending = FALSE", "is_transfer = FALSE"]; p = []
        if start_date: f.append("posted >= %s"); p.append(start_date)
        if end_date: f.append("posted <= %s"); p.append(end_date)
        if account_id: f.append("account_id = %s"); p.append(account_id)
        cur.execute(f"SELECT COALESCE(payee, description, 'Unknown'), SUM(ABS(amount)), COUNT(*) FROM transactions WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 2 DESC LIMIT %s", p + [limit])
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"payee": r[0], "total": float(r[1]), "count": r[2]} for r in rows]

@app.get("/api/spending/over-time")
def spending_over_time(months: int = 6, account_id: Optional[str] = None):
    conn = db_conn()
    try:
        cur = conn.cursor(); f = ["pending = FALSE", "is_transfer = FALSE"]; p = []
        if account_id: f.append("account_id = %s"); p.append(account_id)
        cur.execute(f"SELECT TO_CHAR(posted, 'YYYY-MM'), SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) FROM transactions WHERE {' AND '.join(f)} GROUP BY 1 ORDER BY 1 DESC LIMIT %s", p + [months])
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"month": r[0], "spending": float(r[1]), "income": float(r[2])} for r in rows]

@app.get("/api/spending/deltas")
def spending_deltas(start_date: Optional[date] = None, end_date: Optional[date] = None):
    now = datetime.now()
    if not start_date: start_date = date(now.year, now.month, 1)
    if not end_date: end_date = date(now.year, 12, 31) if now.month == 12 else date(now.year, now.month + 1, 1) - timedelta(days=1)
    pd = (end_date - start_date).days + 1; pe = start_date - timedelta(days=1); ps = pe - timedelta(days=pd - 1)
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(c.name, 'Uncategorized'), c.color, SUM(ABS(t.amount)) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE AND t.posted >= %s AND t.posted <= %s GROUP BY c.name, c.color", (start_date, end_date))
        current = {r[0]: {"color": r[1] or "#475569", "total": float(r[2])} for r in cur.fetchall()}
        cur.execute("SELECT COALESCE(c.name, 'Uncategorized'), SUM(ABS(t.amount)) FROM transactions t LEFT JOIN categories c ON t.category_id = c.id WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE AND t.posted >= %s AND t.posted <= %s GROUP BY c.name", (ps, pe))
        prior = {r[0]: float(r[1]) for r in cur.fetchall()}
    finally: db_put(conn)
    results = []
    for cat in sorted(set(list(current.keys()) + list(prior.keys()))):
        ct = current.get(cat, {}).get("total", 0); pt = prior.get(cat, 0); d = ct - pt
        pct = ((d / pt) * 100) if pt > 0 else (100 if ct > 0 else 0)
        results.append({"category": cat, "color": current.get(cat, {}).get("color", "#475569"), "current": ct, "previous": pt, "delta": round(d, 2), "pct_change": round(pct, 1)})
    results.sort(key=lambda x: abs(x["delta"]), reverse=True)
    tc = sum(r["current"] for r in results); tp = sum(r["previous"] for r in results)
    return {"deltas": results, "totals": {"current": round(tc, 2), "previous": round(tp, 2), "delta": round(tc - tp, 2)}, "period": {"current": {"start": start_date.isoformat(), "end": end_date.isoformat()}, "previous": {"start": ps.isoformat(), "end": pe.isoformat()}}}

# ── Subscriptions ──
@app.get("/api/subscriptions/detect")
def detect_subscriptions(min_months: int = 3, amount_tolerance_pct: float = 15):
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT COALESCE(payee, description), posted, amount FROM transactions WHERE amount < 0 AND pending = FALSE AND is_transfer = FALSE AND COALESCE(payee, description) IS NOT NULL ORDER BY 1, posted"); rows = cur.fetchall()
    finally: db_put(conn)
    by_payee = defaultdict(list)
    for label, posted, amount in rows: by_payee[label].append({"posted": posted, "amount": float(amount)})
    subs = []
    for payee, txns in by_payee.items():
        if len(txns) < min_months: continue
        amounts = [abs(t["amount"]) for t in txns]; med = sorted(amounts)[len(amounts) // 2]
        if med < 1: continue
        tol = med * (amount_tolerance_pct / 100)
        con = sorted([t for t in txns if abs(abs(t["amount"]) - med) <= tol], key=lambda t: t["posted"])
        if len(con) < max(min_months, 2): continue
        gaps = [(con[i]["posted"] - con[i-1]["posted"]).days for i in range(1, len(con))]
        avg = sum(gaps) / len(gaps) if gaps else 0
        if avg < 20 or avg > 45: continue
        last = con[-1]
        subs.append({"payee": payee, "typical_amount": round(med, 2), "annual_cost": round(med * 12, 2), "frequency_days": round(avg, 0), "charge_count": len(con), "last_date": last["posted"].isoformat(), "last_amount": round(abs(last["amount"]), 2)})
    subs.sort(key=lambda s: s["annual_cost"], reverse=True)
    ta = sum(s["annual_cost"] for s in subs)
    return {"subscriptions": subs, "totals": {"annual": round(ta, 2), "monthly": round(ta / 12, 2)}}

# ── Budgets ──
@app.get("/api/budgets")
def get_budgets():
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("SELECT b.id, b.category_id, c.name, c.color, b.monthly_amount FROM budgets b JOIN categories c ON b.category_id = c.id ORDER BY c.sort_order, c.name"); rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "category_id": r[1], "category": r[2], "color": r[3], "monthly_amount": float(r[4])} for r in rows]

class BudgetCreate(BaseModel):
    category_id: int; monthly_amount: float

@app.post("/api/budgets", status_code=201)
def create_or_update_budget(body: BudgetCreate):
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("INSERT INTO budgets (category_id, monthly_amount) VALUES (%s, %s) ON CONFLICT (category_id) DO UPDATE SET monthly_amount = EXCLUDED.monthly_amount RETURNING id", (body.category_id, body.monthly_amount))
        new_id = cur.fetchone()[0]; conn.commit()
    finally: db_put(conn)
    return {"id": new_id}

@app.delete("/api/budgets/{budget_id}")
def delete_budget(budget_id: int):
    conn = db_conn()
    try: cur = conn.cursor(); cur.execute("DELETE FROM budgets WHERE id = %s", (budget_id,)); conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

@app.get("/api/budgets/status")
def budget_status(start_date: Optional[date] = None, end_date: Optional[date] = None):
    now = datetime.now()
    if not start_date: start_date = date(now.year, now.month, 1)
    if not end_date: end_date = date(now.year, 12, 31) if now.month == 12 else date(now.year, now.month + 1, 1) - timedelta(days=1)
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT b.id, b.category_id, c.name, c.color, c.group_name, b.monthly_amount FROM budgets b JOIN categories c ON b.category_id = c.id ORDER BY c.sort_order, c.name")
        budgets = cur.fetchall()
        if not budgets: return {"budgets": [], "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}
        cur.execute("SELECT t.category_id, SUM(ABS(t.amount)) FROM transactions t WHERE t.amount < 0 AND t.pending = FALSE AND t.is_transfer = FALSE AND t.posted >= %s AND t.posted <= %s GROUP BY t.category_id", (start_date, end_date))
        actuals = {r[0]: float(r[1]) for r in cur.fetchall()}
    finally: db_put(conn)
    tb = ts = 0; results = []
    for b in budgets:
        ba = float(b[5]); sp = actuals.get(b[1], 0); tb += ba; ts += sp
        results.append({"budget_id": b[0], "category_id": b[1], "category": b[2], "color": b[3], "group": b[4], "budget": ba, "spent": sp, "remaining": ba - sp, "pct": round((sp / ba * 100) if ba > 0 else 0, 1)})
    return {"budgets": results, "totals": {"budget": tb, "spent": ts, "remaining": tb - ts, "pct": round((ts / tb * 100) if tb > 0 else 0, 1)}, "period": {"start": start_date.isoformat(), "end": end_date.isoformat()}}

# ── Feedback ──
class FeedbackCreate(BaseModel):
    type: str = "feature"  # bug, feature, feedback
    message: str

@app.post("/api/feedback", status_code=201)
def create_feedback(body: FeedbackCreate):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    valid = {"bug", "feature", "feedback"}
    fb_type = body.type if body.type in valid else "feedback"
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO feedback (type, message) VALUES (%s, %s) RETURNING id, created_at",
                    (fb_type, body.message.strip()))
        row = cur.fetchone(); conn.commit()
    finally: db_put(conn)
    return {"id": row[0], "created_at": row[1].isoformat()}

@app.get("/api/feedback")
def get_feedback():
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, type, message, created_at, notion_page_id FROM feedback ORDER BY created_at DESC")
        rows = cur.fetchall()
    finally: db_put(conn)
    return [{"id": r[0], "type": r[1], "message": r[2], "created_at": r[3].isoformat(),
             "synced": r[4] is not None} for r in rows]

@app.delete("/api/feedback/{fb_id}")
def delete_feedback(fb_id: int):
    conn = db_conn()
    try:
        cur = conn.cursor(); cur.execute("DELETE FROM feedback WHERE id = %s", (fb_id,)); conn.commit()
    finally: db_put(conn)
    return {"status": "ok"}

# ── AI Categorization ──
OPENROUTER_KEY_FILE = Path("/run/secrets/openrouter_key")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-001"

def _get_openrouter_key() -> str:
    if OPENROUTER_KEY_FILE.exists(): return OPENROUTER_KEY_FILE.read_text().strip()
    k = os.environ.get("OPENROUTER_API_KEY", ""); return k if k else (_ for _ in ()).throw(RuntimeError("OpenRouter key not found"))

def _call_openrouter(prompt: str) -> str:
    key = _get_openrouter_key()
    req = urllib.request.Request(OPENROUTER_API_URL, data=json.dumps({"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}]}).encode(), method="POST", headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "HTTP-Referer": "https://cp7.dev", "X-Title": "Finance Hub"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e: raise RuntimeError(f"OpenRouter error {e.code}: {e.read().decode()}")

def _build_ai_prompt(txns, categories):
    cl = "\n".join("  - " + c["name"] for c in sorted(categories, key=lambda x: x["name"]))
    ls = [f"  {i+1}. [{t.get('posted','')}] {t.get('payee') or t.get('description') or 'Unknown'} | ${float(t.get('amount',0)):.2f}" for i, t in enumerate(txns)]
    return f"You are a personal finance categorizer.\n\nAVAILABLE CATEGORIES:\n{cl}\n\nTRANSACTIONS:\n" + "\n".join(ls) + '\n\nRules:\n- Match each to exactly one category.\n- If nothing fits, use "Uncategorized".\n- Return ONLY a JSON array.\n- Format: [{"index": 1, "category": "Groceries", "confidence": "high"}, ...]\n- Confidence: "high", "medium", "low"'

def _parse_ai_response(raw):
    raw = raw.strip()
    if raw.startswith("```"): raw = raw.split("```")[1]; raw = raw[4:] if raw.startswith("json") else raw
    return json.loads(raw.strip())

@app.get("/api/categorize/suggest")
def categorize_suggest(limit: int = 100):
    conn = db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT t.id, t.posted, t.amount, t.description, t.payee FROM transactions t WHERE t.category_id IS NULL AND t.pending = FALSE AND t.category_manual = FALSE ORDER BY t.posted DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        if not rows: return {"suggestions": [], "message": "No uncategorized transactions found"}
        txns = [{"id": r[0], "posted": r[1].isoformat() if r[1] else None, "amount": float(r[2]) if r[2] else 0, "description": r[3], "payee": r[4]} for r in rows]
        cur.execute("SELECT id, name, color FROM categories ORDER BY name")
        categories = [{"id": r[0], "name": r[1], "color": r[2]} for r in cur.fetchall()]
        cur.execute("SELECT match_pattern, category_id, c.name, payee_name FROM payee_rules r LEFT JOIN categories c ON r.category_id = c.id ORDER BY r.priority DESC, r.id")
        rules = [{"pattern": r[0], "category_id": r[1], "category": r[2], "payee_name": r[3]} for r in cur.fetchall()]
    finally: db_put(conn)
    rule_results, unknowns = [], []
    for txn in txns:
        key = (txn.get("payee") or txn.get("description") or "").lower(); matched = None
        for rule in rules:
            if rule["pattern"] and rule["pattern"] in key: matched = rule; break
        if matched: rule_results.append({"txn_id": txn["id"], "payee": txn.get("payee") or txn.get("description") or "Unknown", "posted": txn["posted"], "amount": txn["amount"], "category": matched["category"], "category_id": matched["category_id"], "confidence": "rule", "source": "rule"})
        else: unknowns.append(txn)
    ai_results = []
    if unknowns:
        try:
            parsed = _parse_ai_response(_call_openrouter(_build_ai_prompt(unknowns, categories)))
            cat_map = {c["name"]: c for c in categories}; sugg_map = {s["index"]: s for s in parsed}
            for i, txn in enumerate(unknowns, 1):
                sugg = sugg_map.get(i, {}); cn = sugg.get("category", "Uncategorized"); co = cat_map.get(cn)
                ai_results.append({"txn_id": txn["id"], "payee": txn.get("payee") or txn.get("description") or "Unknown", "posted": txn["posted"], "amount": txn["amount"], "category": cn, "category_id": co["id"] if co else None, "confidence": sugg.get("confidence", "low"), "source": "ai"})
        except Exception as e: logger.error("AI categorization failed: %s", e); raise HTTPException(status_code=502, detail="AI error: " + str(e))
    return {"suggestions": rule_results + ai_results, "categories": [{"id": c["id"], "name": c["name"], "color": c["color"]} for c in categories], "stats": {"total": len(txns), "rule_matched": len(rule_results), "ai_suggested": len(ai_results)}}

class CategorizeApplyItem(BaseModel):
    txn_id: str; category_id: int; make_rule: bool = False; payee: Optional[str] = None

class CategorizeApplyRequest(BaseModel):
    items: list[CategorizeApplyItem]

@app.post("/api/categorize/apply")
def categorize_apply(body: CategorizeApplyRequest):
    conn = db_conn(); applied = rules_created = 0
    try:
        cur = conn.cursor()
        for item in body.items:
            cur.execute("UPDATE transactions SET category_id = %s, category_manual = TRUE, updated_at = NOW() WHERE id = %s", (item.category_id, item.txn_id)); applied += 1
            if item.make_rule and item.payee:
                pattern = item.payee.lower().strip()
                cur.execute("SELECT id FROM payee_rules WHERE match_pattern = %s", (pattern,))
                if not cur.fetchone(): cur.execute("INSERT INTO payee_rules (match_pattern, payee_name, category_id, priority) VALUES (%s, %s, %s, 0)", (pattern, item.payee, item.category_id)); rules_created += 1
        conn.commit()
    finally: db_put(conn)
    return {"applied": applied, "rules_created": rules_created}
