#!/usr/bin/env bash
# Еженедельный бэкап clickhouse-backup.
# Схема: create на ноде -> копирование ТОЛЬКО нового снимка в /mnt/backup ->
#        удаление снимка на ноде. Ретеншн ведётся в /mnt/backup (без rsync --delete!).
#
# Почему не зеркало (--delete): после переноса снимок удаляется на ноде, и зеркало
# снесло бы его и из /mnt/backup. Поэтому копируем только новый каталог и чистим архив сами.
#
# create пишет файлы от UID clickhouse в контейнере (~101); /mnt/backup доступен под sudo —
# копирование/чистка идут через sudo. Для cron без пароля в /etc/sudoers.d/dwh-backup:
#   userdwh ALL=(ALL) NOPASSWD: /usr/bin/rsync, /usr/bin/mkdir, /usr/bin/find, /usr/bin/rm
#
# 30 2 * * 0 .../ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1

set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose_cluster.yml}"
BACKUP_NAME="weekly_$(date -u +%Y-%m-%dT%H-%M-%S)"

CLICKHOUSE_LOCAL_BACKUP="${CLICKHOUSE_LOCAL_BACKUP:-/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01/backup}"
BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup}"
# Сколько последних снимков хранить в /mnt/backup.
BACKUPS_TO_KEEP_ARCHIVE="${BACKUPS_TO_KEEP_ARCHIVE:-4}"
# auto | always | never — использовать ли sudo для доступа к /mnt/backup.
BACKUP_SUDO="${BACKUP_SUDO:-auto}"

cd "$COMPOSE_DIR"

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
  case "$BACKUP_SUDO" in
    always) return 0 ;;
    never)  return 1 ;;
    *)      can_write_archive && return 1 || return 0 ;;
  esac
}

if need_sudo; then SUDO="sudo"; else SUDO=""; fi

# 1. Создать снимок на ноде (в каталоге данных — нужны hardlink'и с той же ФС).
docker compose -f "$COMPOSE_FILE" --profile backup run --rm clickhouse-backup create "$BACKUP_NAME"

# 2. Скопировать ТОЛЬКО новый снимок в /mnt/backup (без --delete).
$SUDO mkdir -p "$BACKUP_ARCHIVE/$BACKUP_NAME"
$SUDO rsync -a --numeric-ids \
  "$CLICKHOUSE_LOCAL_BACKUP/$BACKUP_NAME/" \
  "$BACKUP_ARCHIVE/$BACKUP_NAME/"

# 3. Убедиться, что копия на месте и непустая, прежде чем удалять с ноды.
if ! $SUDO test -d "$BACKUP_ARCHIVE/$BACKUP_NAME/metadata"; then
  echo "ОШИБКА: копия $BACKUP_ARCHIVE/$BACKUP_NAME выглядит неполной — снимок на ноде НЕ удаляю" >&2
  exit 1
fi
echo "Скопировано в архив: $BACKUP_ARCHIVE/$BACKUP_NAME"

# 4. Удалить снимок на ноде (через сам clickhouse-backup — корректно и без проблем с правами).
docker compose -f "$COMPOSE_FILE" --profile backup run --rm clickhouse-backup delete local "$BACKUP_NAME"
echo "Удалён локальный снимок на ноде: $BACKUP_NAME"

# 5. Ретеншн в /mnt/backup: оставить BACKUPS_TO_KEEP_ARCHIVE последних weekly_*.
mapfile -t OLD < <($SUDO find "$BACKUP_ARCHIVE" -maxdepth 1 -type d -name 'weekly_*' -printf '%P\n' \
  | sort -r | tail -n +"$((BACKUPS_TO_KEEP_ARCHIVE + 1))")

for d in "${OLD[@]}"; do
  [[ -n "$d" ]] && $SUDO rm -rf "$BACKUP_ARCHIVE/$d" && echo "Удалён старый снимок в архиве: $d"
done
