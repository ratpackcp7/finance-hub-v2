#!/usr/bin/env python3
"""
P0 Patch: Add HTML escaping to prevent XSS from bank-imported data.
Also sanitize CSV export against formula injection.
Run from /home/chris/docker/finance-hub-v2/
"""
import re

# ── 1. Patch index.html: add esc() helper and use it in critical template literals ──

html_path = "app/static/index.html"
with open(html_path, "r") as f:
    html = f.read()

# Add esc() function right after the fmt/fmtDate/api utility functions
esc_fn = """function esc(s){if(s==null)return'';const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
"""

# Insert after the first line that defines api()
marker = "async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});if(!r.ok)throw new Error(await r.text());return r.json();}"
if "function esc(" not in html:
    html = html.replace(marker, marker + "\n" + esc_fn)
    print("✓ Added esc() function")
else:
    print("⊘ esc() already present")

# Now escape critical user-controlled data in template literals.
# Key patterns: ${t.payee}, ${t.description}, ${t.account_name}, ${r.pattern},
# ${r.payee_name}, ${s.payee}, ${p.txn1.description}, ${p.txn2.description},
# ${s.error_message}, ${e.message} in HTML contexts

# Transaction table rows - payee and description
html = html.replace("${tb}${t.payee||t.description||'—'}", "${tb}${esc(t.payee||t.description||'—')}")
html = html.replace("${t.description}</div>", "${esc(t.description)}</div>")
html = html.replace("${t.account_name||''}", "${esc(t.account_name||'')}")

# Transaction modal
html = html.replace("$('mt-desc-display').textContent=t.description||t.payee||'Unknown';",
                     "$('mt-desc-display').textContent=t.description||t.payee||'Unknown';")  # textContent is already safe

# Rule rows
html = html.replace("${r.pattern}</code>", "${esc(r.pattern)}</code>")
html = html.replace("${r.payee_name||'—'}", "${esc(r.payee_name||'—')}")

# Category badge function - escape category name
old_badge = "return`<span class=\"badge\" style=\"background:${col}22;color:${col}\">${name}</span>`;"
new_badge = "return`<span class=\"badge\" style=\"background:${col}22;color:${col}\">${esc(name)}</span>`;"
html = html.replace(old_badge, new_badge)

# Category settings list - escape names
html = html.replace("${c.name}</td>", "${esc(c.name)}</td>")
html = html.replace("${c.group||'—'}", "${esc(c.group||'—')}")

# Account settings - org and name
html = html.replace("${a.org||'—'}", "${esc(a.org||'—')}")
html = html.replace("${a.name}</td>", "${esc(a.name)}</td>")

# Transfer modal - descriptions and account names
html = html.replace("${p.txn1.description||'—'}", "${esc(p.txn1.description||'—')}")
html = html.replace("${p.txn2.description||'—'}", "${esc(p.txn2.description||'—')}")
html = html.replace("${p.txn1.account_name}", "${esc(p.txn1.account_name)}")
html = html.replace("${p.txn2.account_name}", "${esc(p.txn2.account_name)}")

# AI categorize - payee
html = html.replace("${s.payee}</div>", "${esc(s.payee)}</div>")

# Subscription list - payee
html = html.replace("${s.payee}</td>", "${esc(s.payee)}</td>")

# Spending bars - category and payee names
html = html.replace("${c.category}</div>", "${esc(c.category)}</div>")
html = html.replace("${p.payee}</div>", "${esc(p.payee)}</div>")

# Sync log error messages
html = html.replace("${s.error_message||''}", "${esc(s.error_message||'')}")

# Error display in modals
html = html.replace("'Error: '+e.message", "'Error: '+esc(e.message)")

with open(html_path, "w") as f:
    f.write(html)
print("✓ Patched index.html with esc() calls")


# ── 2. Patch main.py: sanitize CSV export against formula injection ──

main_path = "app/main.py"
with open(main_path, "r") as f:
    main_py = f.read()

# Add CSV sanitization helper
csv_helper = '''
def _csv_safe(val):
    """Prefix cell values that could be interpreted as spreadsheet formulas."""
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@', '\\t', '\\r'):
        return "'" + s
    return s

'''

# Insert before the first route handler
if "_csv_safe" not in main_py:
    # Insert after the ACCOUNT_TYPES line
    insert_after = 'ACCOUNT_TYPES = {"checking", "savings", "credit", "investment", "retirement", "529", "utma", "hsa", "brokerage", "loan", "mortgage", "other"}'
    main_py = main_py.replace(insert_after, insert_after + "\n" + csv_helper)
    print("✓ Added _csv_safe() to main.py")

# Now patch the CSV export to use _csv_safe
old_csv_row = 'for r in rows: w.writerow([r[0].isoformat() if r[0] else "", r[1], r[2], r[3], r[4], f"{float(r[5]):.2f}" if r[5] is not None else "", "Yes" if r[6] else "", r[7] or ""])'
new_csv_row = 'for r in rows: w.writerow([r[0].isoformat() if r[0] else "", _csv_safe(r[1]), _csv_safe(r[2]), _csv_safe(r[3]), _csv_safe(r[4]), f"{float(r[5]):.2f}" if r[5] is not None else "", "Yes" if r[6] else "", _csv_safe(r[7] or "")])'

if old_csv_row in main_py:
    main_py = main_py.replace(old_csv_row, new_csv_row)
    print("✓ Patched CSV export with _csv_safe()")
else:
    print("⚠ Could not find CSV export row pattern — check manually")

with open(main_path, "w") as f:
    f.write(main_py)

print("\n✅ All P0 patches applied. Run build.sh to rebuild.")
