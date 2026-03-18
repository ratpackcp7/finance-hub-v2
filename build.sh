#!/usr/bin/env bash
# Finance Hub v2 — build helper
# Run from /home/chris/docker/finance-hub-v2/
set -e
echo "→ Building and starting containers"
docker compose up -d --build
echo "✓ Done. App: http://localhost:8888"
