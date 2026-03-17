#!/usr/bin/env bash
# Finance Hub v2 — build helper
# Copies shared files and brings containers up.
# Run from /home/chris/docker/finance-hub-v2/
set -e

echo "→ Copying shared syncer.py to worker/"
cp app/syncer.py worker/syncer.py

echo "→ Building and starting containers"
docker compose up -d --build

echo "✓ Done. App: http://localhost:8888"
