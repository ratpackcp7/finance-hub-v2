"""
Finance Hub v2 — FastAPI application (v4.2.0)
P2: AI categorization privacy/provenance
P3: Raw payload retention policy
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import close_pool, db_conn, db_put
from migrate import run_migrations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = db_conn()
        logger.info("DB pool ready")
        run_migrations(conn)
        db_put(conn)
    except Exception as e:
        logger.error("Startup failed: %s", e)
    yield
    close_pool()


app = FastAPI(title="Finance Hub", version="4.2.0", lifespan=lifespan)
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
