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

from db import close_pool, get_pool
from migrate import run_migrations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = get_pool().getconn()
    try:
        logger.info("DB pool ready")
        run_migrations(conn)
        app.state.ready = True
    except Exception:
        app.state.ready = False
        logger.exception("Startup failed")
        raise
    finally:
        get_pool().putconn(conn)
    yield
    close_pool()


app = FastAPI(title="Finance Hub", version="4.6.0", lifespan=lifespan)
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
from routers.splits import router as splits_router
from routers.tags import router as tags_router
from routers.bills import router as bills_router
from routers.goals import router as goals_router
from routers.review import router as review_router
from routers.digest import router as digest_router
from routers.bulk import router as bulk_router
from routers.compare import router as compare_router
from routers.merchants import router as merchants_router
from routers.forecast import router as forecast_router
from routers.benchmark import router as benchmark_router
from routers.inv_txns import router as inv_txns_router

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
app.include_router(splits_router)
app.include_router(tags_router)
app.include_router(bills_router)
app.include_router(goals_router)
app.include_router(review_router)
app.include_router(digest_router)
app.include_router(bulk_router)
app.include_router(compare_router)
app.include_router(merchants_router)
app.include_router(forecast_router)
app.include_router(benchmark_router)
app.include_router(inv_txns_router)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    if not getattr(app.state, "ready", False):
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
