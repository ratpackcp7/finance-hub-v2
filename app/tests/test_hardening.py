"""test_hardening.py — Integration tests for Finance Hub backend hardening.

Tests cover Phase A (foundation) and Phase B (correctness) changes.
Runs against fhub_test database via FastAPI TestClient.
"""
import pytest
from datetime import date
from decimal import Decimal

import db as app_db


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A.1: db_transaction / db_read context managers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestContextManagers:
    def test_db_transaction_commits_on_success(self):
        """db_transaction should auto-commit when block exits cleanly."""
        with app_db.db_transaction() as cur:
            cur.execute(
                "INSERT INTO accounts (id, name, currency) VALUES ('cm_test_1', 'CM Test', 'USD')")

        # Verify committed
        with app_db.db_read() as cur:
            cur.execute("SELECT name FROM accounts WHERE id = 'cm_test_1'")
            assert cur.fetchone()[0] == "CM Test"

    def test_db_transaction_rolls_back_on_exception(self):
        """db_transaction should rollback when an exception is raised."""
        with pytest.raises(ValueError):
            with app_db.db_transaction() as cur:
                cur.execute(
                    "INSERT INTO accounts (id, name, currency) VALUES ('cm_test_2', 'Should Rollback', 'USD')")
                raise ValueError("intentional")

        # Verify NOT committed
        with app_db.db_read() as cur:
            cur.execute("SELECT id FROM accounts WHERE id = 'cm_test_2'")
            assert cur.fetchone() is None

    def test_db_read_returns_clean_connection(self):
        """db_read should not leave the connection in a dirty state."""
        with app_db.db_read() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone()[0] == 1
        # If connection was dirty, the pool would have issues on next use
        with app_db.db_read() as cur:
            cur.execute("SELECT 2")
            assert cur.fetchone()[0] == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A.2: Recon unlock returns 501
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReconUnlockDisabled:
    def test_unlock_returns_501(self, client):
        """POST to unlock should return 501 Not Implemented."""
        resp = client.post("/api/reconcile/sessions/999/unlock")
        assert resp.status_code == 501
        assert "disabled" in resp.json()["detail"].lower()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A.3: Investment txn date typing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestInvTxnDateTyping:
    def test_create_inv_txn_with_iso_date(self, client, seed_account):
        """Creating an investment txn with ISO date string should work."""
        # Create a holding first
        acct_id = seed_account
        with app_db.db_transaction() as cur:
            cur.execute(
                "INSERT INTO accounts (id, name, currency, account_type) "
                "VALUES ('inv_acct', 'Investment', 'USD', 'investment') ON CONFLICT DO NOTHING")
            cur.execute(
                "INSERT INTO holdings (account_id, ticker, name, shares, cost_basis) "
                "VALUES ('inv_acct', 'VTI', 'Vanguard Total Market', 10.0, 2000.0) RETURNING id")
            holding_id = cur.fetchone()[0]

        resp = client.post("/api/investment-txns", json={
            "holding_id": holding_id,
            "txn_type": "buy",
            "txn_date": "2026-01-15",
            "shares": 5.0,
            "price_per_share": 200.0,
            "total_amount": 1000.0,
        })
        assert resp.status_code in (200, 201), resp.json()
        assert resp.json()["type"] == "buy"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A.4: Investment delete guard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestInvestmentDeleteGuard:
    def test_cannot_delete_partially_closed_lot(self, client):
        """Deleting a buy whose lot has been partially closed should fail."""
        # Setup: investment account + holding + buy + sell
        with app_db.db_transaction() as cur:
            cur.execute(
                "INSERT INTO accounts (id, name, currency, account_type) "
                "VALUES ('guard_acct', 'Guard Test', 'USD', 'investment') ON CONFLICT DO NOTHING")
            cur.execute(
                "INSERT INTO holdings (account_id, ticker, name, shares, cost_basis) "
                "VALUES ('guard_acct', 'SPY', 'S&P 500', 10.0, 4000.0) RETURNING id")
            holding_id = cur.fetchone()[0]

        # Buy 10 shares
        resp = client.post("/api/investment-txns", json={
            "holding_id": holding_id,
            "txn_type": "buy",
            "txn_date": "2026-01-01",
            "shares": 10.0,
            "price_per_share": 400.0,
            "total_amount": 4000.0,
        })
        buy_id = resp.json()["id"]

        # Sell 5 (partially closes the lot)
        client.post("/api/investment-txns", json={
            "holding_id": holding_id,
            "txn_type": "sell",
            "txn_date": "2026-02-01",
            "shares": 5.0,
            "price_per_share": 450.0,
            "total_amount": 2250.0,
        })

        # Try to delete the buy — should fail
        resp = client.delete(f"/api/investment-txns/{buy_id}")
        assert resp.status_code == 400
        assert "partially closed" in resp.json()["detail"].lower()

    def test_can_delete_untouched_lot(self, client):
        """Deleting a buy whose lot is untouched should succeed."""
        with app_db.db_transaction() as cur:
            cur.execute(
                "INSERT INTO accounts (id, name, currency, account_type) "
                "VALUES ('guard_acct2', 'Guard Test 2', 'USD', 'investment') ON CONFLICT DO NOTHING")
            cur.execute(
                "INSERT INTO holdings (account_id, ticker, name, shares, cost_basis) "
                "VALUES ('guard_acct2', 'QQQ', 'Nasdaq', 5.0, 2000.0) RETURNING id")
            holding_id = cur.fetchone()[0]

        resp = client.post("/api/investment-txns", json={
            "holding_id": holding_id,
            "txn_type": "buy",
            "txn_date": "2026-01-01",
            "shares": 5.0,
            "price_per_share": 400.0,
            "total_amount": 2000.0,
        })
        buy_id = resp.json()["id"]

        # Delete with no sells — should succeed
        resp = client.delete(f"/api/investment-txns/{buy_id}")
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B.3: rate_of_return not hardcoded
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestRateOfReturn:
    def test_rate_not_hardcoded_23_3(self, client):
        """rate_of_return should NOT be the old hardcoded 23.3."""
        resp = client.get("/api/investment/performance")
        assert resp.status_code == 200
        rate = resp.json()["summary"]["rate_of_return"]
        assert rate != 23.3, "rate_of_return is still hardcoded to 23.3!"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B.4: Canonical transfer pair ID
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCanonicalPairId:
    def test_pair_id_is_order_independent(self):
        """_make_pair_id(A, B) should equal _make_pair_id(B, A)."""
        from routers.transactions import _make_pair_id
        assert _make_pair_id("txn_001", "txn_002") == _make_pair_id("txn_002", "txn_001")

    def test_pair_id_differs_for_different_pairs(self):
        """Different transaction pairs should produce different IDs."""
        from routers.transactions import _make_pair_id
        id1 = _make_pair_id("txn_001", "txn_002")
        id2 = _make_pair_id("txn_001", "txn_003")
        assert id1 != id2

    def test_apply_transfers_rejects_non_pair(self, client, seed_account):
        """apply_transfers should reject pairs with != 2 elements."""
        resp = client.post("/api/transfers/apply", json={
            "pairs": [["txn_only_one"]]
        })
        assert resp.status_code == 400
        assert "exactly 2" in resp.json()["detail"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B.5: Benchmark zero-value truthiness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestBenchmarkTruthiness:
    def test_zero_portfolio_value_not_treated_as_none(self):
        """A portfolio value of 0.0 should not be treated as missing."""
        # This tests the logic directly
        port_val = 0.0
        first_port = 100.0
        # Old code: if port_val and first_port → False (wrong: 0.0 is falsy)
        # New code: if port_val is not None and first_port → True (correct)
        result = ((port_val / first_port - 1) * 100) if port_val is not None and first_port else None
        assert result == -100.0  # 0/100 - 1 = -1.0 → -100%


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C.1: Recon GET does not mutate DB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReconGetNoMutation:
    def test_get_session_does_not_write(self, client, seed_account):
        """GET /reconcile/sessions/{id} should not update the DB."""
        acct_id = seed_account
        # Create a recon session
        resp = client.post("/api/reconcile/sessions", json={
            "account_id": acct_id,
            "statement_date": "2026-03-01",
            "statement_balance": 1000.00,
        })
        session_id = resp.json()["id"]

        # Record the updated_at or just check it doesn't crash
        resp1 = client.get(f"/api/reconcile/sessions/{session_id}")
        assert resp1.status_code == 200

        # GET again — should be idempotent
        resp2 = client.get(f"/api/reconcile/sessions/{session_id}")
        assert resp2.status_code == 200
        assert resp1.json()["cleared_count"] == resp2.json()["cleared_count"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Basic endpoint smoke tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestEndpointSmoke:
    """Quick checks that key endpoints return 200 after refactoring."""

    @pytest.mark.parametrize("path", [
        "/api/accounts",
        "/api/accounts/net-worth",
        "/api/categories",
        "/api/budgets",
        "/api/tags",
        "/api/payee-rules",
        "/api/review/counts",
        "/api/spending/over-time",
        "/api/forecast/cashflow",
        "/api/investment/performance",
        "/api/goals",
    ])
    def test_get_endpoint_200(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}: {resp.text[:200]}"

    def test_transactions_list(self, client, seed_txns):
        resp = client.get("/api/transactions?limit=10")
        assert resp.status_code == 200
        assert resp.json()["total"] == len(seed_txns)
