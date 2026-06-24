#!/usr/bin/env bash
# Еженедельный бэкап clickhouse-backup.
# Локально: .../data/clickhouse01/backup/ (тот же диск, что store/shadow — нужны hardlink'и).
# Зеркало: rsync на BACKUP_ARCHIVE после create.
#
# create пишет файлы от UID clickhouse в контейнере (~101) — userdwh их не читает.
# rsync по умолчанию через sudo; для cron без пароля:
#   userdwh ALL=(ALL) NOPASSWD: /usr/bin/rsync
# или: BACKUP_RSYNC_USE_SUDO=never и добавить userdwh в группу с GID clickhouse на хосте.
#
# 30 2 * * 0 .../ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose_cluster.yml}"
BACKUP_NAME="weekly_$(date -u +%Y-%m-%dT%H-%M-%S)"

CLICKHOUSE_LOCAL_BACKUP="${CLICKHOUSE_LOCAL_BACKUP:-/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01/backup}"
BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/home/userdwh/backup/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup}"
# auto | always | never
BACKUP_RSYNC_USE_SUDO="${BACKUP_RSYNC_USE_SUDO:-auto}"

cd "$COMPOSE_DIR"

docker compose -f "$COMPOSE_FILE" --profile backup run --rm clickhouse-backup create "$BACKUP_NAME"

can_read_backup_tree() {
  [[ -d "$CLICKHOUSE_LOCAL_BACKUP" && -r "$CLICKHOUSE_LOCAL_BACKUP" && -x "$CLICKHOUSE_LOCAL_BACKUP" ]] || return 1
  local dir
  shopt -s nullglob
  for dir in "$CLICKHOUSE_LOCAL_BACKUP"/*/; do
    [[ -r "$dir" && -x "$dir" ]] || return 1
  done
  shopt -u nullglob
  return 0
}

sync_backup_archive() {
  mkdir -p "$BACKUP_ARCHIVE"
  local -a opts=(-a --numeric-ids --delete)
  local src="${CLICKHOUSE_LOCAL_BACKUP%/}/"
  local dst="${BACKUP_ARCHIVE%/}/"

  if [[ "$BACKUP_RSYNC_USE_SUDO" == "always" ]]; then
    sudo rsync "${opts[@]}" "$src" "$dst"
    return
  fi

  if [[ "$BACKUP_RSYNC_USE_SUDO" == "never" ]]; then
    rsync "${opts[@]}" "$src" "$dst"
    return
  fi

  if can_read_backup_tree; then
    rsync "${opts[@]}" "$src" "$dst"
    return
  fi

  echo "rsync: нет прав на backup/ (владелец — UID clickhouse в Docker), копируем через sudo" >&2
  sudo rsync "${opts[@]}" "$src" "$dst"
}

sync_backup_archive
