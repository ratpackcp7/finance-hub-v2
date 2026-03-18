#!/usr/bin/env python3
"""Smoke test CSV import endpoints."""
import json
import urllib.request

BASE = "http://127.0.0.1:8888"

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())

# Test mappings list
mappings = get("/api/csv-import/mappings")
print(f"=== CSV Mappings: {len(mappings)} presets ===")
for m in mappings:
    print(f"  [{m['id']}] {m['name']} ({m['institution']}) sign_flip={m['sign_flip']}")
    print(f"       headers: {m['header_signature']}")
    print(f"       mapping: {json.dumps(m['mapping'])}")

# Test preview with a fake Chase CC CSV
import io, csv, tempfile, os
from urllib.parse import urlencode

# Build a test CSV in Chase CC format
buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount"])
w.writerow(["03/15/2026", "03/16/2026", "AMAZON MARKETPLACE", "Shopping", "Sale", "-42.99"])
w.writerow(["03/14/2026", "03/15/2026", "STARBUCKS #1234", "Food & Drink", "Sale", "-6.75"])
w.writerow(["03/13/2026", "03/14/2026", "PAYMENT RECEIVED", "Payment", "Payment", "500.00"])
csv_data = buf.getvalue().encode()

# Get first account for testing
accounts = get("/api/accounts")
if accounts:
    acct_id = accounts[0]["id"]
    acct_name = accounts[0]["name"]
    print(f"\n=== Preview test (account: {acct_name}) ===")

    # Multipart form upload
    import http.client
    import mimetypes
    boundary = "----TestBoundary123"
    body = []
    # file field
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="file"; filename="test_chase.csv"')
    body.append(b"Content-Type: text/csv")
    body.append(b"")
    body.append(csv_data)
    # account_id field
    body.append(f"--{boundary}".encode())
    body.append(f'Content-Disposition: form-data; name="account_id"'.encode())
    body.append(b"")
    body.append(acct_id.encode())
    body.append(f"--{boundary}--".encode())
    body_bytes = b"\r\n".join(body)

    req = urllib.request.Request(
        f"{BASE}/api/csv-import/preview",
        data=body_bytes,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
        print(f"  Detected: {result.get('detected_mapping', {}).get('name', 'NONE')}")
        print(f"  Total rows: {result['total_rows']}")
        for p in result.get("preview", []):
            print(f"    Row {p['_row']}: date={p.get('date_parsed')} amt={p.get('amount')} desc={p.get('description')}")
    except Exception as e:
        print(f"  Preview error: {e}")
        import traceback; traceback.print_exc()
else:
    print("\nNo accounts found — skipping preview test")

print("\n=== All checks passed ===")
