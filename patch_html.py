#!/usr/bin/env python3
"""Patch index.html with expanded account types and enhanced net worth display."""
import re

path = "/home/chris/docker/finance-hub-v2/app/static/index.html"
with open(path) as f:
    html = f.read()

# 1. Expand account type dropdown
old_types = "const typeOpts=['checking','savings','credit','investment','loan','other'];"
new_types = "const typeOpts=['checking','savings','credit','investment','retirement','529','utma','hsa','loan','mortgage','other'];"
html = html.replace(old_types, new_types)

# 2. Enhance net worth display with asset class breakdown
old_nw = "$('ds-acct-count').textContent=accts.length+' accounts';"
new_nw = """const nwSub=(netWorth.summary||[]).map(s=>{const color=s.class==='liabilities'?'#fca5a5':s.class==='liquid'?'#86efac':'#94a3b8';return`<span style="color:${color}">${s.label}: ${fmt(s.total)}</span>`;}).join(' \\u00b7 ');$('ds-acct-count').innerHTML=nwSub||(accts.length+' accounts');"""
html = html.replace(old_nw, new_nw)

with open(path, "w") as f:
    f.write(html)

# Verify
with open(path) as f:
    content = f.read()
assert "retirement" in content, "typeOpts not updated"
assert "nwSub" in content, "net worth display not updated"
print("OK: patched index.html")
