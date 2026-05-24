#!/usr/bin/env bash
# Еженедельный бэкап ClickHouse (clickhouse-backup) в /mnt/backup без перезапуска clickhouse01.
# Расписание (суббота → воскресенье, ночь): например 02:30 по локальному времени сервера в воскресенье:
#   30 2 * * 0 /path/to/ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1
#
# Перед первым запуском: mkdir -p на хосте для каталога бэкапов и права для UID/GID clickhouse
# в контейнере (обычно uid 101), либо chmod 777 на тест (не рекомендуется для прода).

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose_cluster.yml}"
BACKUP_NAME="weekly_$(date -u +%Y-%m-%dT%H-%M-%S)"

cd "$COMPOSE_DIR"

docker compose -f "$COMPOSE_FILE" --profile backup run --rm \
  -e LOG_LEVEL=info \
  clickhouse-backup \
  create "$BACKUP_NAME"
