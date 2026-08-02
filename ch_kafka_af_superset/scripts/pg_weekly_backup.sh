#!/usr/bin/env bash
# Еженедельный бэкап PostgreSQL (контейнер postgres из docker-compose_af.yml).
# pg_dumpall снимает ВСЕ базы (airflow, superset, ...) + роли/пароли одним файлом.
# Дамп пишется сразу в /mnt/backup (доступ только под sudo) в виде .sql.gz.
#
# Для cron без пароля в /etc/sudoers.d/ch-backup-rsync (те же бинарники):
#   userdwh ALL=(ALL) NOPASSWD: /usr/bin/tee, /bin/mkdir, /usr/bin/find
#
# 45 2 * * 0 .../pg_weekly_backup.sh >> /var/log/pg_weekly_backup.log 2>&1

set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-postgres}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"

# Отдельный подкаталог: сюда пишутся только дампы postgres.
BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/mnt/backup/DWH_cluster/ch_kafka_af_superset/postgres_backup}"
BACKUPS_TO_KEEP="${BACKUPS_TO_KEEP:-5}"
# auto | always | never — использовать ли sudo для доступа к приёмнику.
BACKUP_SUDO="${BACKUP_SUDO:-auto}"

DUMP_NAME="pg_all_$(date -u +%Y-%m-%dT%H-%M-%S).sql.gz"

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

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  echo "Ошибка: контейнер '$PG_CONTAINER' не запущен" >&2
  exit 1
fi

if need_sudo; then SUDO="sudo"; else SUDO=""; fi

$SUDO mkdir -p "$BACKUP_ARCHIVE"

# pg_dumpall в stdout -> gzip -> файл в архиве. pipefail ловит ошибку дампа.
docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" \
  pg_dumpall -U "$PG_USER" --clean --if-exists \
  | gzip -c \
  | $SUDO tee "$BACKUP_ARCHIVE/$DUMP_NAME" > /dev/null

echo "Готово: $BACKUP_ARCHIVE/$DUMP_NAME"

# Ротация: оставить BACKUPS_TO_KEEP последних файлов pg_all_*.sql.gz.
mapfile -t OLD < <($SUDO find "$BACKUP_ARCHIVE" -maxdepth 1 -name 'pg_all_*.sql.gz' -printf '%T@ %p\n' \
  | sort -rn | tail -n +"$((BACKUPS_TO_KEEP + 1))" | cut -d' ' -f2-)

for f in "${OLD[@]}"; do
  [[ -n "$f" ]] && $SUDO rm -f "$f" && echo "Удалён старый бэкап: $f"
done
