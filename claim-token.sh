#!/usr/bin/env bash
# Finance Hub v2 — claim a SimpleFIN setup token
# Usage: ./claim-token.sh <setup-token>
# Writes the resulting Access URL to secrets/simplefin_access_url

set -e

TOKEN="${1:-}"

if [ -z "$TOKEN" ]; then
  echo "Usage: ./claim-token.sh <setup-token>"
  exit 1
fi

echo "→ Decoding setup token..."
CLAIM_URL="$(echo "$TOKEN" | base64 --decode)"

echo "→ Claiming access URL from SimpleFIN..."
ACCESS_URL="$(curl -s -X POST -H 'Content-Length: 0' "$CLAIM_URL")"

if [ -z "$ACCESS_URL" ]; then
  echo "✗ Claim failed — empty response. Token may already be used."
  exit 1
fi

if echo "$ACCESS_URL" | grep -q '"error"'; then
  echo "✗ Claim failed: $ACCESS_URL"
  exit 1
fi

echo "✓ Access URL claimed successfully"

mkdir -p secrets
echo "$ACCESS_URL" > secrets/simplefin_access_url
echo "✓ Written to secrets/simplefin_access_url"
echo ""
echo "Access URL (keep this safe):"
echo "$ACCESS_URL"
