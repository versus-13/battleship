#!/usr/bin/env bash
# Postgres dump into ./backups, keep 14 days. Cron: 0 4 * * * /opt/battleship/backup.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M)
docker compose exec -T db pg_dump -U battleship -Fc battleship > "backups/battleship-$stamp.dump"
find backups -name "battleship-*.dump" -mtime +14 -delete
echo "backups/battleship-$stamp.dump"
