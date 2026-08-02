#!/usr/bin/env bash
# Еженедельный бэкап clickhouse-backup.
# Локально: .../data/clickhouse01/backup/ (тот же диск, что store/shadow — нужны hardlink'и).
# Зеркало: rsync на BACKUP_ARCHIVE (/mnt/backup) после create.
#
# create пишет файлы от UID clickhouse в контейнере (~101) — userdwh их не читает.
# BACKUP_ARCHIVE (/mnt/backup) доступен только под sudo — mkdir и rsync идут через sudo.
# Для cron без пароля в /etc/sudoers.d/ch-backup-rsync:
#   userdwh ALL=(ALL) NOPASSWD: /usr/bin/rsync, /bin/mkdir
#
# 30 2 * * 0 .../ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose_cluster.yml}"
BACKUP_NAME="weekly_$(date -u +%Y-%m-%dT%H-%M-%S)"

CLICKHOUSE_LOCAL_BACKUP="${CLICKHOUSE_LOCAL_BACKUP:-/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01/backup}"
# Отдельный подкаталог, т.к. rsync --delete очищает приёмник целиком.
BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup}"
# auto | always | never — использовать ли sudo для доступа к приёмнику.
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

# Приёмник (/mnt/backup) пишем без sudo, только если каталог реально доступен на запись.
can_write_archive() {
  local probe="$BACKUP_ARCHIVE"
  while [[ ! -e "$probe" && "$probe" == */* ]]; do
    probe="${probe%/*}"
    [[ -z "$probe" ]] && probe="/"
  done
  [[ -w "$probe" ]]
}

need_sudo() {
  case "$BACKUP_RSYNC_USE_SUDO" in
    always) return 0 ;;
    never)  return 1 ;;
    *)      { can_read_backup_tree && can_write_archive; } && return 1 || return 0 ;;
  esac
}

sync_backup_archive() {
  local -a opts=(-a --numeric-ids --delete)
  local src="${CLICKHOUSE_LOCAL_BACKUP%/}/"
  local dst="${BACKUP_ARCHIVE%/}/"

  if need_sudo; then
    echo "rsync: приёмник /mnt/backup или локальный backup/ требуют прав root — используем sudo" >&2
    sudo mkdir -p "$BACKUP_ARCHIVE"
    sudo rsync "${opts[@]}" "$src" "$dst"
  else
    mkdir -p "$BACKUP_ARCHIVE"
    rsync "${opts[@]}" "$src" "$dst"
  fi
}

sync_backup_archive
