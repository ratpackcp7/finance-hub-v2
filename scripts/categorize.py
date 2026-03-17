#!/usr/bin/env python3
"""
AI-assisted transaction categorizer for Finance Hub v2.
Uses OpenRouter API (https://openrouter.ai).

How it works:
  1. Load payee rules from the app
  2. Auto-apply rules to matching transactions (no AI needed)
  3. Send remaining unknowns to AI for suggestions
  4. You review AI suggestions interactively
  5. On approval, write a payee rule so the same payee is auto-applied next time

Usage:
  python3 categorize.py              # uncategorized only
  python3 categorize.py --all        # re-categorize everything (skips manual)
  python3 categorize.py --batch 20   # AI batch size (default 25)
  python3 categorize.py --dry-run    # show what would happen, apply nothing
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8888"
OPENROUTER_KEY_FILE = Path("/home/chris/docker/finance-hub-v2/secrets/openrouter_key")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Swap options: google/gemini-2.5-flash-lite, openai/gpt-4o-mini, anthropic/claude-3-haiku
OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-001"
DEFAULT_BATCH = 25

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_openrouter_key():
    if OPENROUTER_KEY_FILE.exists():
        return OPENROUTER_KEY_FILE.read_text().strip()
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k
    sys.exit("ERROR: No OpenRouter API key found. Put it in secrets/openrouter_key or set OPENROUTER_API_KEY env var.")


def _api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code} on GET {path}: {e.read().decode()}")


def _api_patch(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ⚠  PATCH failed {e.code}: {e.read().decode()}")
        return None


def _api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ⚠  POST failed {e.code}: {e.read().decode()}")
        return None


def _openrouter(prompt, key):
    payload = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_API_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://cp7.dev",
            "X-Title": "Finance Hub Categorizer",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            resp = json.loads(r.read())
            return resp["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        sys.exit(f"OpenRouter API error {e.code}: {e.read().decode()}")


def _color(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return _color(t, "92")
def yellow(t): return _color(t, "93")
def cyan(t):   return _color(t, "96")
def dim(t):    return _color(t, "2")
def bold(t):   return _color(t, "1")


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_transactions(include_all=False):
    data = _api_get("/api/transactions?limit=2000&offset=0")
    txns = data.get("transactions", data) if isinstance(data, dict) else data
    if not include_all:
        txns = [t for t in txns if not t.get("category_id") or not t.get("category_manual")]
    return txns


def fetch_categories():
    cats = _api_get("/api/categories")
    if isinstance(cats, dict) and "categories" in cats:
        cats = cats["categories"]
    return {c["name"]: c["id"] for c in cats}


def fetch_payee_rules():
    rules = _api_get("/api/payee-rules")
    if isinstance(rules, dict):
        rules = list(rules.values())[0] if rules else []
    return rules


# ── Rule matching ─────────────────────────────────────────────────────────────

def txn_key(txn):
    return (txn.get("payee") or txn.get("description") or "").lower()


def apply_rules(txns, rules):
    rule_matches = []
    unknowns = []
    for txn in txns:
        key = txn_key(txn)
        matched = None
        best_priority = -999
        for rule in rules:
            pattern = rule.get("pattern", "").lower()
            if pattern and pattern in key:
                if rule.get("priority", 0) >= best_priority:
                    matched = rule
                    best_priority = rule.get("priority", 0)
        if matched:
            rule_matches.append((txn, matched))
        else:
            unknowns.append(txn)
    return rule_matches, unknowns


# ── AI suggestion ─────────────────────────────────────────────────────────────

def build_prompt(txns, categories):
    cat_list = "\n".join(f"  - {name}" for name in sorted(categories.keys()))
    txn_lines = []
    for i, t in enumerate(txns):
        amount = t.get("amount", 0) or 0
        payee  = t.get("payee") or t.get("description") or "Unknown"
        date   = t.get("posted") or t.get("date") or ""
        txn_lines.append(f"  {i+1}. [{date}] {payee} | ${float(amount):.2f}")
    return (
        "You are a personal finance categorizer. Suggest the best category for each transaction.\n\n"
        "AVAILABLE CATEGORIES:\n" + cat_list + "\n\n"
        "TRANSACTIONS:\n" + "\n".join(txn_lines) + "\n\n"
        "Rules:\n"
        "- Match each transaction to exactly one category from the list above.\n"
        "- If nothing fits, use \"Uncategorized\".\n"
        "- Return ONLY a JSON array, no explanation, no markdown fences.\n"
        '- Format: [{"index": 1, "category": "Groceries", "confidence": "high"}, ...]\n'
        '- Confidence: "high" (obvious), "medium" (reasonable guess), "low" (unclear)'
    )


def ask_ai_batch(txns, categories, key):
    raw = _openrouter(build_prompt(txns, categories), key).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        print(yellow("  ⚠  Model returned unparseable JSON. Skipping batch."))
        print(dim(raw[:500]))
        return []


# ── Apply + save rule ─────────────────────────────────────────────────────────

def apply_txn(txn, cat_id, dry_run=False):
    if dry_run:
        return True
    result = _api_patch(f"/api/transactions/{txn['id']}", {"category_id": cat_id})
    return result is not None


def save_rule(txn, cat_name, cat_id, dry_run=False):
    payee = txn.get("payee") or txn.get("description") or ""
    if not payee:
        return
    pattern = payee.lower().strip()
    if dry_run:
        print(dim("  [dry-run] Would create rule: '" + pattern + "' -> " + cat_name))
        return
    result = _api_post("/api/payee-rules", {
        "match_pattern": pattern,
        "payee_name": txn.get("payee") or payee,
        "category_id": cat_id,
        "priority": 0,
    })
    if result:
        print(dim("  -> Rule saved: '" + pattern + "' -> " + cat_name))


# ── Interactive review ────────────────────────────────────────────────────────

def review_batch(txns, suggestions, categories, dry_run=False):
    approved = []
    cat_names = sorted(categories.keys())
    sugg_map = {s["index"]: s for s in suggestions}

    print()
    for i, txn in enumerate(txns, 1):
        sugg       = sugg_map.get(i, {})
        cat_name   = sugg.get("category", "?")
        confidence = sugg.get("confidence", "?")
        amount     = float(txn.get("amount") or 0)
        payee      = txn.get("payee") or txn.get("description") or "Unknown"
        date       = txn.get("posted") or txn.get("date") or ""

        conf_color = green if confidence == "high" else yellow if confidence == "medium" else dim
        print(bold("[" + str(i) + "/" + str(len(txns)) + "] " + payee) + dim("  " + date + "  $" + f"{amount:.2f}"))
        print("  Suggested: " + conf_color(cat_name) + " " + dim("(" + confidence + ")"))
        if dry_run:
            print(dim("  [dry-run mode — nothing will be saved]"))
        print(dim("  [Enter]=accept+rule  [o]=accept only (no rule)  [e]=edit  [s]=skip  [a]=accept all  [q]=quit"))

        while True:
            try:
                choice = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                return approved

            if choice in ("", "y"):
                cat_id = categories.get(cat_name)
                if cat_id:
                    approved.append((txn, cat_name, cat_id, True))
                    print(green("  ✓ Accepted + rule saved"))
                else:
                    print(yellow("  ⚠  '" + cat_name + "' not in category list. Skipping."))
                break

            elif choice == "o":
                cat_id = categories.get(cat_name)
                if cat_id:
                    approved.append((txn, cat_name, cat_id, False))
                    print(green("  ✓ Accepted (no rule)"))
                else:
                    print(yellow("  ⚠  '" + cat_name + "' not in category list. Skipping."))
                break

            elif choice == "e":
                print("  Categories: " + ", ".join(cat_names))
                new_cat = input("  Enter category: ").strip()
                cat_id = categories.get(new_cat)
                if cat_id:
                    save_rule_choice = input("  Save as rule? [Y/n] ").strip().lower()
                    make_rule = save_rule_choice != "n"
                    approved.append((txn, new_cat, cat_id, make_rule))
                    suffix = " + rule" if make_rule else ""
                    print(green("  ✓ Set to '" + new_cat + "'" + suffix))
                else:
                    print(yellow("  ⚠  '" + new_cat + "' not found. Skipping."))
                break

            elif choice == "s":
                print(dim("  — Skipped"))
                break

            elif choice == "q":
                print("Quitting. Applying approved so far...")
                return approved

            elif choice == "a":
                print(green("  ✓ Accepting all remaining..."))
                cat_id = categories.get(cat_name)
                if cat_id:
                    approved.append((txn, cat_name, cat_id, True))
                for j in range(i, len(txns)):
                    t  = txns[j]
                    s  = sugg_map.get(j + 1, {})
                    cn = s.get("category", "")
                    ci = categories.get(cn)
                    if ci:
                        approved.append((t, cn, ci, True))
                return approved

            else:
                print(dim("  ? [Enter]=accept+rule  [o]=accept only  [e]=edit  [s]=skip  [a]=accept all  [q]=quit"))

    return approved


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI-assisted transaction categorizer (OpenRouter)")
    parser.add_argument("--all",     action="store_true", help="Re-categorize all transactions (skips manually-set ones)")
    parser.add_argument("--batch",   type=int, default=DEFAULT_BATCH, help=f"AI batch size (default {DEFAULT_BATCH})")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without applying anything")
    args = parser.parse_args()

    key        = _get_openrouter_key()
    categories = fetch_categories()
    rules      = fetch_payee_rules()

    if not categories:
        sys.exit("ERROR: No categories found. Add some in the Finance Hub UI first.")

    print(cyan("Loaded " + str(len(categories)) + " categories, " + str(len(rules)) + " payee rules."))
    if args.dry_run:
        print(yellow("DRY RUN — nothing will be written.\n"))

    txns = fetch_transactions(include_all=args.all)
    if not txns:
        print(green("No transactions to process. Done."))
        return

    # ── Phase 1: rule matching ───────────────────────────────────────────────
    rule_matches, unknowns = apply_rules(txns, rules)

    if rule_matches:
        print(bold("\n── Phase 1: Rule matches (" + str(len(rule_matches)) + ") ──────────────────────────"))
        applied = 0
        for txn, rule in rule_matches:
            payee   = txn.get("payee") or txn.get("description") or "?"
            cat     = rule.get("category", "?")
            cat_id  = rule.get("category_id")
            pattern = rule.get("pattern", "")
            print("  " + green("✓") + " " + payee + "  ->  " + cat + "  " + dim("[rule: " + pattern + "]"))
            if not args.dry_run and cat_id:
                apply_txn(txn, cat_id)
                applied += 1
        print(dim("  Applied " + str(applied) + " rule-based categorizations."))

    if not unknowns:
        print(green("\nAll transactions matched by rules. No AI needed."))
        return

    # ── Phase 2: AI for unknowns ─────────────────────────────────────────────
    print(bold("\n── Phase 2: AI suggestions (" + str(len(unknowns)) + " unknown transactions) ──────────"))
    print(dim("Model: " + OPENROUTER_MODEL))

    total_approved = 0

    for start in range(0, len(unknowns), args.batch):
        batch = unknowns[start:start + args.batch]
        end   = min(start + args.batch, len(unknowns))
        print(bold("\n  Batch " + str(start // args.batch + 1) + ": " + str(start + 1) + "-" + str(end)))
        print(dim("  Asking AI..."))

        suggestions = ask_ai_batch(batch, categories, key)
        if not suggestions:
            print(yellow("  No suggestions returned. Skipping batch."))
            continue

        approved = review_batch(batch, suggestions, categories, dry_run=args.dry_run)

        for txn, cat_name, cat_id, make_rule in approved:
            apply_txn(txn, cat_id, dry_run=args.dry_run)
            if make_rule:
                save_rule(txn, cat_name, cat_id, dry_run=args.dry_run)
            total_approved += 1

        if end < len(unknowns):
            cont = input(cyan("\nContinue to next batch? [Enter=yes / q=quit] ")).strip().lower()
            if cont == "q":
                break

    print(bold(cyan("\nDone. " + str(len(rule_matches)) + " rule-matched + " + str(total_approved) + " AI-categorized.")))


if __name__ == "__main__":
    main()
