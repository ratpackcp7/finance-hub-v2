"""
Finance Hub v2 — FastAPI application (v4.0.0)
P2: Split into routers + shared db module
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import close_pool, db_conn, db_put

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


def run_migrations():
    conn = db_conn()
    try:
        cur = conn.cursor()

        # ── Core schema ──
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
        cur.execute("""CREATE TABLE IF NOT EXISTS balance_snapshots (
            id SERIAL PRIMARY KEY, snapshot_date DATE NOT NULL, account_id TEXT NOT NULL,
            account_name TEXT, account_type TEXT, balance NUMERIC(15,2),
            created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(snapshot_date, account_id))""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_snap_date ON balance_snapshots(snapshot_date)")

        # ── Cleanup: drop deprecated household_id ──
        for tbl in ("accounts", "transactions", "categories", "payee_rules", "budgets", "feedback", "balance_snapshots"):
            cur.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS household_id")
        for idx in ("idx_acct_household", "idx_txn_household", "idx_cat_household", "idx_rules_household"):
            cur.execute(f"DROP INDEX IF EXISTS {idx}")

        # ── Import batch tracking ──
        cur.execute("""CREATE TABLE IF NOT EXISTS import_batches (
            id SERIAL PRIMARY KEY, started_at TIMESTAMPTZ DEFAULT NOW(), finished_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'running', source TEXT NOT NULL DEFAULT 'simplefin',
            raw_payload JSONB, accounts_seen INT DEFAULT 0, txns_added INT DEFAULT 0,
            txns_updated INT DEFAULT 0, txns_skipped INT DEFAULT 0, dupes_flagged INT DEFAULT 0,
            error_message TEXT)""")
        cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS import_batch_id INT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_batch ON transactions(import_batch_id)")
        cur.execute("""CREATE TABLE IF NOT EXISTS duplicate_flags (
            id SERIAL PRIMARY KEY, txn_id TEXT NOT NULL, duplicate_of TEXT NOT NULL,
            reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            batch_id INT, created_at TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_dupe_status ON duplicate_flags(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_dupe_batch ON duplicate_flags(batch_id)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dupe_pair ON duplicate_flags(txn_id, duplicate_of)")

        # ── Audit log ──
        cur.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            action TEXT NOT NULL, field_name TEXT, old_value TEXT, new_value TEXT,
            source TEXT NOT NULL DEFAULT 'user', created_at TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC)")

        # ── Soft delete columns ──
        for tbl in ("categories", "payee_rules", "budgets", "feedback"):
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")

        conn.commit()
        logger.info("Migrations complete")
    except Exception as e:
        conn.rollback()
        logger.error("Migration failed: %s", e)
    finally:
        db_put(conn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = db_conn()
        db_put(conn)
        logger.info("DB pool ready")
        run_migrations()
    except Exception as e:
        logger.error("DB pool init failed: %s", e)
    yield
    close_pool()


app = FastAPI(title="Finance Hub", version="4.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Register routers ──
from routers.accounts import router as accounts_router
from routers.transactions import router as transactions_router
from routers.categories import router as categories_router
from routers.rules import router as rules_router
from routers.spending import router as spending_router, sub_router as subscriptions_router
from routers.budgets import router as budgets_router
from routers.sync import router as sync_router
from routers.imports import router as imports_router
from routers.categorize import router as categorize_router
from routers.feedback import router as feedback_router
from routers.audit import router as audit_router

app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(categories_router)
app.include_router(rules_router)
app.include_router(spending_router)
app.include_router(subscriptions_router)
app.include_router(budgets_router)
app.include_router(sync_router)
app.include_router(imports_router)
app.include_router(categorize_router)
app.include_router(feedback_router)
app.include_router(audit_router)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
