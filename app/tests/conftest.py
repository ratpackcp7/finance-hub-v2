"""conftest.py — Test fixtures for Finance Hub integration tests.

Patches the DB pool to use fhub_test instead of fhub.
Provides fixtures for seeding test data and cleanup.
"""
import os
import psycopg2
import psycopg2.pool
import pytest

# Force DB_NAME to test database BEFORE importing app code
os.environ["DB_NAME"] = "fhub_test"

import db as app_db


def _get_test_pool():
    """Create a connection pool pointed at fhub_test."""
    pw = open("/run/secrets/db_password").read().strip()
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1, maxconn=5,
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname="fhub_test",
        user=os.environ.get("DB_USER", "fhub"),
        password=pw,
    )


@pytest.fixture(scope="session", autouse=True)
def patch_db_pool():
    """Replace the app's DB pool with one connected to fhub_test."""
    pool = _get_test_pool()
    app_db._pool = pool
    yield
    pool.closeall()


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate mutable tables before each test."""
    conn = app_db.get_pool().getconn()
    try:
        cur = conn.cursor()
        # Order matters due to FK constraints
        cur.execute("""
            TRUNCATE TABLE
                transaction_splits, transaction_tags, reconciliation_session_items,
                reconciliation_sessions, duplicate_flags, goal_snapshots, savings_goals,
                tax_lots, investment_transactions, holding_snapshots, holdings,
                benchmark_prices, investment_performance, balance_snapshots,
                import_batches, feedback, budgets, audit_log,
                transactions, payee_rules, accounts
            CASCADE
        """)
        # Re-seed categories if empty
        cur.execute("SELECT count(*) FROM categories")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO categories (name, color, group_name, sort_order, is_income) VALUES
                    ('Groceries', '#22c55e', 'Food', 10, FALSE),
                    ('Dining Out', '#86efac', 'Food', 11, FALSE),
                    ('Payroll', '#4ade80', 'Income', 90, TRUE),
                    ('Uncategorized', '#475569', NULL, 999, FALSE)
                ON CONFLICT (name) DO NOTHING
            """)
        conn.commit()
    finally:
        app_db.get_pool().putconn(conn)
    yield


@pytest.fixture
def seed_account():
    """Insert a test account and return its ID."""
    acct_id = "test_acct_001"
    with app_db.db_transaction() as cur:
        cur.execute(
            "INSERT INTO accounts (id, name, currency, balance, on_budget) "
            "VALUES (%s, 'Test Checking', 'USD', 1000.00, TRUE) "
            "ON CONFLICT DO NOTHING",
            (acct_id,))
    return acct_id


@pytest.fixture
def seed_txns(seed_account):
    """Insert a few test transactions."""
    acct_id = seed_account
    txns = []
    with app_db.db_transaction() as cur:
        for i, (amt, desc) in enumerate([
            (-50.00, "Walmart grocery"),
            (-12.99, "Netflix subscription"),
            (2500.00, "Direct deposit payroll"),
            (-200.00, "Transfer out"),
        ]):
            txn_id = f"test_txn_{i:03d}"
            cur.execute(
                "INSERT INTO transactions (id, account_id, posted, amount, description, pending) "
                "VALUES (%s, %s, CURRENT_DATE, %s, %s, FALSE)",
                (txn_id, acct_id, amt, desc))
            txns.append(txn_id)
    return txns


@pytest.fixture
def client():
    """FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)
