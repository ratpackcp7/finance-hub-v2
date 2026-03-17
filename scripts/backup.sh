#!/bin/bash
# Finance Hub — daily Postgres backup
# Keeps 7 days of rolling backups in /home/chris/backups/fhub/

BACKUP_DIR="/home/chris/backups/fhub"
CONTAINER="fhub-db"
DB_NAME="fhub"
DB_USER="fhub"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y-%m-%d_%H%M)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting fhub backup..."

# Dump via docker exec (no password needed — pg_dump runs as postgres inside container)
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists \
  | gzip > "$BACKUP_DIR/fhub_${TIMESTAMP}.sql.gz"

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_DIR/fhub_${TIMESTAMP}.sql.gz" | cut -f1)
    echo "[$(date)] Backup OK: fhub_${TIMESTAMP}.sql.gz ($SIZE)"
else
    echo "[$(date)] ERROR: pg_dump failed"
    exit 1
fi

# Prune old backups
find "$BACKUP_DIR" -name "fhub_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
REMAINING=$(ls -1 "$BACKUP_DIR"/fhub_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Pruned backups older than ${RETENTION_DAYS} days. ${REMAINING} backups on disk."
