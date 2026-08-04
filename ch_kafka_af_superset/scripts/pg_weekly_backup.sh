#!/usr/bin/env bash
# Еженедельный бэкап PostgreSQL с ноды ClickHouse.
# Postgres крутится на другой ноде (docker-compose_af.yml, IP по умолчанию 192.168.14.225).
# С этой ноды: временный контейнер с клиентом pg_dumpall -> TCP 5432 на удалённом хосте,
# дамп сразу в /mnt/backup (доступ только под sudo) в виде .sql.gz.
#
# Для cron без пароля в /etc/sudoers.d/dwh-backup:
#   userdwh ALL=(ALL) NOPASSWD: /usr/bin/tee, /usr/bin/mkdir, /usr/bin/find, /usr/bin/rm
#
# 45 2 * * 0 .../pg_weekly_backup.sh >> /var/log/pg_weekly_backup.log 2>&1

set -euo pipefail

# Удалённый Postgres (нода Airflow / docker-compose_af.yml).
PG_HOST="${PG_HOST:-192.168.14.225}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-postgres}"
# Образ только как клиент pg_dumpall (на этой ноде контейнер postgres не нужен).
PG_CLIENT_IMAGE="${PG_CLIENT_IMAGE:-postgres:16}"

BACKUP_ARCHIVE="${BACKUP_ARCHIVE:-/mnt/backup/DWH_cluster/ch_kafka_af_superset/postgres_backup}"
BACKUPS_TO_KEEP="${BACKUPS_TO_KEEP:-5}"
BACKUP_SUDO="${BACKUP_SUDO:-auto}"

DUMP_NAME="pg_all_$(date -u +%Y-%m-%dT%H-%M-%S).sql.gz"

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

# Проверка доступности удалённого Postgres (клиент в одноразовом контейнере).
if ! docker run --rm -e PGPASSWORD="$PG_PASSWORD" "$PG_CLIENT_IMAGE" \
  pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" >/dev/null 2>&1; then
  echo "Ошибка: PostgreSQL недоступен на ${PG_HOST}:${PG_PORT} (пользователь ${PG_USER})" >&2
  exit 1
fi

$SUDO mkdir -p "$BACKUP_ARCHIVE"

# pg_dumpall по сети -> gzip -> /mnt/backup. pipefail ловит ошибку дампа.
docker run --rm -e PGPASSWORD="$PG_PASSWORD" "$PG_CLIENT_IMAGE" \
  pg_dumpall -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" --clean --if-exists \
  | gzip -c \
  | $SUDO tee "$BACKUP_ARCHIVE/$DUMP_NAME" > /dev/null

echo "Готово: $BACKUP_ARCHIVE/$DUMP_NAME (источник ${PG_HOST}:${PG_PORT})"

mapfile -t OLD < <($SUDO find "$BACKUP_ARCHIVE" -maxdepth 1 -name 'pg_all_*.sql.gz' -printf '%T@ %p\n' \
  | sort -rn | tail -n +"$((BACKUPS_TO_KEEP + 1))" | cut -d' ' -f2-)

for f in "${OLD[@]}"; do
  [[ -n "$f" ]] && $SUDO rm -f "$f" && echo "Удалён старый бэкап: $f"
done
