# Finance Hub v2

Self-hosted personal finance dashboard powered by SimpleFIN.

## Stack
- **Backend**: FastAPI (Python 3.12), PostgreSQL 16
- **Worker**: APScheduler daily SimpleFIN sync (no Redis needed)
- **Frontend**: Vanilla HTML/JS + Chart.js, dark theme
- **Infrastructure**: Docker Compose, port 8888 → NPM → finance.cp7.dev

## First-time setup

### 1. Create secrets
```bash
cd /home/chris/docker/finance-hub-v2
mkdir -p secrets

# Paste your SimpleFIN Access URL (NOT the setup token — the claimed access URL)
echo "https://user:pass@bridge.simplefin.org/..." > secrets/simplefin_access_url

# Random DB password
openssl rand -base64 32 > secrets/db_password

# Random app secret
openssl rand -base64 32 > secrets/app_secret_key
```

### 2. Build and start
```bash
chmod +x build.sh
./build.sh
```

### 3. NPM proxy
Add a proxy host in Nginx Proxy Manager:
- Domain: finance.cp7.dev
- Forward to: fhub-app:8000 (or 127.0.0.1:8888)
- Enable Cloudflare / Access as needed

## Daily sync
Worker syncs SimpleFIN at 6:00 AM CT automatically.
Manual sync: click **Sync** button in the UI top-right.

## Resuming after changes
```bash
./build.sh
# or if only app code changed (no dependency changes):
docker compose restart fhub-app
```

## Ports used
- 8888 → fhub-app (FastAPI)
- 5432 → fhub-db (Postgres, internal only)

## Key files
- `app/main.py`     — FastAPI routes
- `app/syncer.py`   — SimpleFIN sync logic (shared with worker)
- `app/static/index.html` — full frontend SPA
- `worker/worker.py` — APScheduler daily sync
- `scripts/init.sql` — DB schema + seeded categories
