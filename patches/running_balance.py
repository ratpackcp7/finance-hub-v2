"""
Patch: Add running balance to Finance Hub v2
Edits main.py and static/index.html
"""
import re

# ── Patch main.py ──
with open("/home/chris/docker/finance-hub-v2/app/main.py", "r") as f:
    main = f.read()

# Replace the get_transactions endpoint
old_get_txns = '''@app.get("/api/transactions")
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
    return {"total": total, "limit": limit, "offset": offset, "transactions": [{"id": r[0], "account_id": r[1], "account_name": r[2], "posted": r[3].isoformat() if r[3] else None, "amount": float(r[4]) if r[4] is not None else None, "description": r[5], "payee": r[6], "category_id": r[7], "category": r[8], "category_manual": r[9], "pending": r[10], "notes": r[11], "is_transfer": r[12]} for r in rows]}'''

new_get_txns = '''@app.get("/api/transactions")
def get_transactions(limit: int = 200, offset: int = 0, account_id: Optional[str] = None, category_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, search: Optional[str] = None, pending: Optional[bool] = None):
    conn = db_conn()
    try:
        cur = conn.cursor()
        filters, params = _txn_filters(account_id, category_id, start_date, end_date, search, pending)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        # When filtered to a single account, compute running balance via window function
        # Balance is calculated over ALL transactions in the account (unfiltered) so it reflects true balance
        if account_id:
            cur.execute(f"""
                WITH bal AS (
                    SELECT id, SUM(amount) OVER (ORDER BY posted ASC, id ASC) AS running_balance
                    FROM transactions WHERE account_id = %s
                )
                SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee,
                       t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer,
                       bal.running_balance
                FROM transactions t
                JOIN accounts a ON t.account_id = a.id
                LEFT JOIN categories c ON t.category_id = c.id
                LEFT JOIN bal ON t.id = bal.id
                {where}
                ORDER BY t.posted DESC, t.id
                LIMIT %s OFFSET %s""", [account_id] + params + [limit, offset])
        else:
            cur.execute(f"SELECT t.id, t.account_id, a.name, t.posted, t.amount, t.description, t.payee, t.category_id, c.name, t.category_manual, t.pending, t.notes, t.is_transfer, NULL as running_balance FROM transactions t JOIN accounts a ON t.account_id = a.id LEFT JOIN categories c ON t.category_id = c.id {where} ORDER BY t.posted DESC, t.id LIMIT %s OFFSET %s", params + [limit, offset])
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) FROM transactions t {where}", params)
        total = cur.fetchone()[0]
    finally: db_put(conn)
    return {"total": total, "limit": limit, "offset": offset, "has_balance": account_id is not None, "transactions": [{"id": r[0], "account_id": r[1], "account_name": r[2], "posted": r[3].isoformat() if r[3] else None, "amount": float(r[4]) if r[4] is not None else None, "description": r[5], "payee": r[6], "category_id": r[7], "category": r[8], "category_manual": r[9], "pending": r[10], "notes": r[11], "is_transfer": r[12], "running_balance": float(r[13]) if r[13] is not None else None} for r in rows]}'''

if old_get_txns in main:
    main = main.replace(old_get_txns, new_get_txns)
    print("✅ Patched get_transactions in main.py")
else:
    print("❌ Could not find get_transactions block in main.py")
    # Try to show what we're looking for
    import sys
    sys.exit(1)

with open("/home/chris/docker/finance-hub-v2/app/main.py", "w") as f:
    f.write(main)

# ── Patch index.html ──
with open("/home/chris/docker/finance-hub-v2/app/static/index.html", "r") as f:
    html = f.read()

# 1. Replace the desktop table header to add Balance column
old_thead = '<thead><tr><th>Date</th><th>Description / Payee</th><th>Account</th><th>Category</th><th style="text-align:right">Amount</th><th></th></tr></thead>'
new_thead = '<thead><tr><th>Date</th><th>Description / Payee</th><th>Account</th><th>Category</th><th style="text-align:right">Amount</th><th class="bal-col" style="text-align:right;display:none">Balance</th><th></th></tr></thead>'

if old_thead in html:
    html = html.replace(old_thead, new_thead)
    print("✅ Patched thead in index.html")
else:
    print("❌ Could not find thead in index.html")

# 2. Replace the loadTxns function's row rendering to include balance column
# Find the row template in the loadTxns function and add balance cell
old_row_end = """<td class="tc-amt ${t.amount<0?'amt-neg':'amt-pos'}" style="text-align:right">${fmt(t.amount)}</td><td class="tc-edit"><button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openTxnModal('${t.id}')">Edit</button></td></tr>`"""

new_row_end = """<td class="tc-amt ${t.amount<0?'amt-neg':'amt-pos'}" style="text-align:right">${fmt(t.amount)}</td><td class="tc-bal bal-col ${t.running_balance!=null?(t.running_balance<0?'amt-neg':'amt-pos'):''}" style="text-align:right;display:none">${t.running_balance!=null?fmt(t.running_balance):''}</td><td class="tc-edit"><button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openTxnModal('${t.id}')">Edit</button></td></tr>`"""

if old_row_end in html:
    html = html.replace(old_row_end, new_row_end)
    print("✅ Patched row template in index.html")
else:
    print("❌ Could not find row template in index.html")

# 3. Add balance column visibility toggle in the loadTxns function
# After the txn-tbody innerHTML assignment, toggle balance column visibility
old_pagination = "$('txn-summary').textContent=`${txnTotal.toLocaleString()} transactions`"
new_pagination = """// Toggle balance column visibility
  const showBal=data.has_balance;document.querySelectorAll('.bal-col').forEach(el=>{el.style.display=showBal?'':'none';});
  $('txn-summary').textContent=`${txnTotal.toLocaleString()} transactions`"""

if old_pagination in html:
    html = html.replace(old_pagination, new_pagination)
    print("✅ Patched balance column toggle in index.html")
else:
    print("❌ Could not find pagination text in index.html")

# 4. Add mobile style for balance column (hide on mobile)
old_mobile_tc_edit = '.tc-edit{display:none}'
new_mobile_tc_edit = '.tc-edit{display:none}\n      .tc-bal{display:none!important}'

if old_mobile_tc_edit in html:
    html = html.replace(old_mobile_tc_edit, new_mobile_tc_edit, 1)
    print("✅ Patched mobile hide for balance column")
else:
    print("❌ Could not find mobile tc-edit rule")

with open("/home/chris/docker/finance-hub-v2/app/static/index.html", "w") as f:
    f.write(html)

print("\n🎉 All patches applied. Restart fhub-app to activate.")
