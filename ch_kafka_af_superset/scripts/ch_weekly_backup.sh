#!/usr/bin/env bash
# Еженедельный бэкап clickhouse-backup.
# Локально: .../data/clickhouse01/backup/ (тот же диск, что store/shadow — нужны hardlink'и).
# Зеркало на репозиторий: rsync в /mnt/backup после успешного create.
#
# 30 2 * * 0 /home/userdwh/DWH_cluster/ch_kafka_af_superset/scripts/ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose_cluster.yml}"
BACKUP_NAME="weekly_$(date -u +%Y-%m-%dT%H-%M-%S)"

CLICKHOUSE_LOCAL_BACKUP="${CLICKHOUSE_LOCAL_BACKUP:-/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01/backup}"
BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/home/userdwh/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup}"

cd "$COMPOSE_DIR"

docker compose -f "$COMPOSE_FILE" --profile backup run --rm clickhouse-backup create "$BACKUP_NAME"

mkdir -p "$BACKUP_ARCHIVE"
rsync -a --numeric-ids --delete "$CLICKHOUSE_LOCAL_BACKUP/" "$BACKUP_ARCHIVE/"
