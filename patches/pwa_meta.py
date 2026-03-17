#!/usr/bin/env python3
"""Patch index.html to add PWA manifest + meta tags."""
import sys

html_path = "/home/chris/docker/finance-hub-v2/app/static/index.html"

with open(html_path, "r") as f:
    content = f.read()

# Check if already patched
if "manifest.json" in content:
    print("Already patched — manifest link found.")
    sys.exit(0)

pwa_tags = """  <link rel="manifest" href="/static/manifest.json">
  <meta name="theme-color" content="#0a0d14">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="apple-touch-icon" href="/static/icon-192.svg">"""

# Insert after <title> line
target = "<title>Finance Hub</title>"
if target not in content:
    print("ERROR: Could not find title tag")
    sys.exit(1)

content = content.replace(target, target + "\n" + pwa_tags)

with open(html_path, "w") as f:
    f.write(content)

print("PWA meta tags injected successfully.")
