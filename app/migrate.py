"""
Finance Hub v2 — Lightweight migration runner.

Tracks applied migrations in a `schema_migrations` table.
Migration files are numbered SQL files in the migrations/ directory.
Each file runs once; the runner applies them in order.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _ensure_tracking_table(cur):
    """Create the schema_migrations table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def _get_applied(cur) -> set[str]:
    """Return set of already-applied migration versions."""
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {r[0] for r in cur.fetchall()}


def _get_pending(applied: set[str]) -> list[tuple[str, str]]:
    """Return list of (version, filepath) for unapplied migrations, sorted."""
    if not MIGRATIONS_DIR.exists():
        logger.warning("No migrations directory found at %s", MIGRATIONS_DIR)
        return []
    pending = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = f.stem  # e.g. "001_baseline"
        if version not in applied:
            pending.append((version, str(f)))
    return pending


def run_migrations(conn) -> int:
    """
    Run all pending migrations. Returns count of migrations applied.
    Each migration runs in its own transaction (committed individually).
    """
    cur = conn.cursor()
    _ensure_tracking_table(cur)
    conn.commit()

    applied = _get_applied(cur)
    pending = _get_pending(applied)

    if not pending:
        logger.info("Migrations: all up to date (%d applied)", len(applied))
        return 0

    count = 0
    for version, filepath in pending:
        logger.info("Applying migration: %s", version)
        try:
            sql = Path(filepath).read_text()
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,))
            conn.commit()
            count += 1
            logger.info("Migration %s applied successfully", version)
        except Exception as e:
            conn.rollback()
            logger.error("Migration %s FAILED: %s", version, e)
            raise RuntimeError(f"Migration {version} failed: {e}") from e

    logger.info("Migrations complete: %d applied, %d total", count, len(applied) + count)
    return count
