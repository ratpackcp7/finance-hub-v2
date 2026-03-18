"""
Finance Hub v2 — FastAPI application (v4.4.0)
Reconciliation workflow + CSV import UI
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import close_pool, db_conn, db_put
from migrate import run_migrations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db_conn()
    try:
        logger.info("DB pool ready")
        run_migrations(conn)
        app.state.ready = True
    except Exception:
        app.state.ready = False
        logger.exception("Startup failed")
        raise
    finally:
        db_put(conn)
    yield
    close_pool()


app = FastAPI(title="Finance Hub", version="4.4.0", lifespan=lifespan)
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
from routers.csv_import import router as csv_import_router
from routers.reconcile import router as reconcile_router
from routers.feedback import router as feedback_router
from routers.audit import router as audit_router
from routers.holdings import router as holdings_router

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
app.include_router(csv_import_router)
app.include_router(reconcile_router)
app.include_router(feedback_router)
app.include_router(audit_router)
app.include_router(holdings_router)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
