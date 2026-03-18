"""Benchmark comparison router — compare portfolio returns against market indices."""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from db import db_conn, db_put

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


@router.get("/compare")
def compare_to_benchmark(benchmark: str = "SPY", period: str = "1Y"):
    """Compare portfolio performance against a benchmark.
    Uses investment_performance table (Vanguard monthly data) vs benchmark_prices.
    period: 1Y, 3Y, 5Y, ALL
    """
    periods = {"1Y": 12, "3Y": 36, "5Y": 60, "ALL": 999}
    months = periods.get(period, 12)

    conn = db_conn()
    try:
        cur = conn.cursor()
        cutoff = date.today() - timedelta(days=months * 31)

        # Portfolio: use investment_performance (Vanguard monthly data)
        cur.execute(
            "SELECT month, ending_balance, cumulative_returns "
            "FROM investment_performance WHERE month >= %s ORDER BY month ASC",
            (cutoff,))
        portfolio = cur.fetchall()

        if not portfolio:
            return {"error": "No investment performance data available",
                    "hint": "Import Vanguard monthly performance data first"}

        # Benchmark: get from benchmark_prices
        cur.execute(
            "SELECT price_date, close_price FROM benchmark_prices "
            "WHERE ticker = %s AND price_date >= %s ORDER BY price_date ASC",
            (benchmark.upper(), cutoff))
        bench_rows = cur.fetchall()

        # If no benchmark data cached, try to fetch it
        if not bench_rows:
            _refresh_benchmark(cur, benchmark.upper(), cutoff)
            cur.execute(
                "SELECT price_date, close_price FROM benchmark_prices "
                "WHERE ticker = %s AND price_date >= %s ORDER BY price_date ASC",
                (benchmark.upper(), cutoff))
            bench_rows = cur.fetchall()
            conn.commit()

    finally:
        db_put(conn)

    # Build monthly comparison
    # Portfolio data is already monthly
    port_months = {r[0].strftime("%Y-%m"): {"balance": float(r[1]) if r[1] else 0,
                                             "cumulative": float(r[2]) if r[2] else 0}
                   for r in portfolio}

    # Convert benchmark daily prices to monthly (use last day of each month)
    bench_monthly = {}
    for price_date, price in bench_rows:
        m = price_date.strftime("%Y-%m")
        bench_monthly[m] = float(price)  # Last one wins (end of month)

    # Align months
    all_months = sorted(set(list(port_months.keys()) + list(bench_monthly.keys())))
    if not all_months:
        return {"error": "No overlapping data between portfolio and benchmark"}

    # Calculate returns
    first_port = None
    first_bench = None
    series = []
    for m in all_months:
        port = port_months.get(m)
        bench = bench_monthly.get(m)

        port_val = port["balance"] if port else None
        bench_val = bench

        if port_val and first_port is None:
            first_port = port_val
        if bench_val and first_bench is None:
            first_bench = bench_val

        port_return = ((port_val / first_port - 1) * 100) if port_val and first_port else None
        bench_return = ((bench_val / first_bench - 1) * 100) if bench_val and first_bench else None

        series.append({
            "month": m,
            "portfolio_value": round(port_val, 2) if port_val else None,
            "portfolio_return": round(port_return, 2) if port_return is not None else None,
            "benchmark_price": round(bench_val, 2) if bench_val else None,
            "benchmark_return": round(bench_return, 2) if bench_return is not None else None,
        })

    # Summary
    last = series[-1] if series else {}
    port_total = last.get("portfolio_return")
    bench_total = last.get("benchmark_return")
    alpha = round(port_total - bench_total, 2) if port_total is not None and bench_total is not None else None

    return {
        "benchmark": benchmark.upper(),
        "period": period,
        "months": len(series),
        "series": series,
        "summary": {
            "portfolio_return": port_total,
            "benchmark_return": bench_total,
            "alpha": alpha,
            "portfolio_start": round(first_port, 2) if first_port else None,
            "portfolio_end": round(last.get("portfolio_value", 0), 2) if last else None,
        },
    }


def _refresh_benchmark(cur, ticker, start_date):
    """Fetch benchmark prices from yfinance and cache in benchmark_prices table."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        hist = tk.history(start=start_date.isoformat(), interval="1wk")
        if hist.empty:
            logger.warning("No yfinance data for %s", ticker)
            return 0
        inserted = 0
        for idx, row in hist.iterrows():
            d = idx.date() if hasattr(idx, 'date') else idx
            price = float(row["Close"])
            cur.execute(
                "INSERT INTO benchmark_prices (ticker, price_date, close_price) "
                "VALUES (%s, %s, %s) ON CONFLICT (ticker, price_date) DO UPDATE SET close_price = EXCLUDED.close_price",
                (ticker, d, price))
            inserted += 1
        logger.info("Cached %d benchmark prices for %s", inserted, ticker)
        return inserted
    except Exception as e:
        logger.error("Benchmark fetch failed for %s: %s", ticker, e)
        return 0


@router.post("/refresh")
def refresh_benchmark_data(ticker: str = "SPY", months: int = 60):
    """Manually refresh benchmark price cache."""
    start = date.today() - timedelta(days=months * 31)
    conn = db_conn()
    try:
        cur = conn.cursor()
        count = _refresh_benchmark(cur, ticker.upper(), start)
        conn.commit()
    finally:
        db_put(conn)
    return {"status": "ok", "ticker": ticker.upper(), "prices_cached": count}
