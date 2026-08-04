# Бэкап ClickHouse (clickhouse01)

Еженедельный бэкап единственного рабочего узла ClickHouse из `docker-compose_cluster.yml`
средствами [`altinity/clickhouse-backup`](https://github.com/Altinity/clickhouse-backup).

- Снимок создаётся **локально** в каталоге данных ClickHouse: `.../data/clickhouse01/backup/`.
- Затем **копируется** на репозиторий `/mnt/backup` (`rsync` только нового снимка, без `--delete`).
- После успешной копии снимок **удаляется на ноде** — на диске данных бэкапы не накапливаются.
- Долговременное хранение и ретеншн — **в `/mnt/backup`** (последние N снимков).
- Расписание — ночь с субботы на воскресенье (cron).

> Почему не зеркало `rsync --delete`: снимок удаляется на ноде после переноса, а зеркало
> удалило бы его и из `/mnt/backup`. Поэтому копируется только новый каталог, а старые в
> архиве чистит сам скрипт по счётчику `BACKUPS_TO_KEEP_ARCHIVE`.

> Прод трогать нельзя. Сервис `clickhouse-backup` объявлен с `profiles: [backup]`,
> поэтому при обычном `docker compose up` он **не запускается** и не влияет на работающий стек.

---

## 1. Как это устроено

### Сервис в compose

```yaml
clickhouse-backup:
  profiles:
    - backup                       # не поднимается при обычном up
  image: altinity/clickhouse-backup:2.6.33
  container_name: clickhouse-backup
  networks:
    click_network: {}
  depends_on:
    - clickhouse01
  volumes:
    - /mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01:/var/lib/clickhouse
    - /home/userdwh/DWH_cluster/ch_kafka_af_superset/config/clickhouse-backup/config.yml:/etc/clickhouse-backup/config.yml:ro
  environment:
    CLICKHOUSE_BACKUP_CONFIG: /etc/clickhouse-backup/config.yml
```

### Ключевое правило: один том

`clickhouse-backup` при `FREEZE` делает **hardlink** из `shadow/` в `backup/`.
Hardlink работает **только внутри одной файловой системы**, поэтому:

```
/mnt/2tb/.../data/clickhouse01  →  /var/lib/clickhouse          (store, shadow)
                                     └── backup/weekly_.../       (та же ФС, hardlink OK)
```

Каталог `backup/` **нельзя** монтировать отдельным томом на `/mnt/backup` — будет
`invalid cross-device link`. Копия на репозиторий делается позже, обычным `rsync`.

### Конфиг `config/clickhouse-backup/config.yml`

```yaml
general:
  backups_to_keep_local: 5         # предохранитель; скрипт всё равно удаляет снимок после копии
  log_level: info

clickhouse:
  host: clickhouse01
  port: 9000                       # native, не 8123
  username: default
  password: ""
  timeout: 2h
  skip_tables:
    - system.*
    - INFORMATION_SCHEMA.*
    - information_schema.*
  skip_table_engines:              # у VIEW нет данных — пропускаем
    - View
    - Live
  backup_mutations: true
  ignore_not_exists_error_during_freeze: true
```

---

## 2. Разовая подготовка сервера

Выполнить один раз перед первым запуском.

### 2.1. Каталог-приёмник на репозитории

```bash
sudo mkdir -p /mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup
```

### 2.2. Права на каталог данных

Локальный `backup/` создаётся процессом **clickhouse** внутри контейнера (UID обычно `101`).
**Нельзя** делать `chown userdwh` или `chmod 777` на дереве данных — это ломает `FREEZE`
у сервера (`Operation not permitted` на `store/.../columns.txt`).

Если права уже были испорчены, вернуть владельца процессу ClickHouse:

```bash
CH_UID=$(docker exec clickhouse01 stat -c '%u' /var/lib/clickhouse)
CH_GID=$(docker exec clickhouse01 stat -c '%g' /var/lib/clickhouse)
DATA=/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01

sudo chown -R "${CH_UID}:${CH_GID}" "$DATA"
sudo find "$DATA" -type d -exec chmod 755 {} \;
sudo find "$DATA" -type f -exec chmod 644 {} \;
```

### 2.3. Права для rsync (cron без пароля)

Приёмник `/mnt/backup/DWH_cluster/ch_kafka_af_superset` доступен **только под `sudo`**, а
локальный `backup/` принадлежит UID clickhouse (`userdwh` его не читает). Поэтому и `mkdir`,
и `rsync` для зеркала скрипт выполняет через `sudo` (режим `auto` определяет это сам).

Чтобы это работало из cron без пароля, создать `/etc/sudoers.d/ch-backup-rsync`:

```text
userdwh ALL=(ALL) NOPASSWD: /usr/bin/rsync, /bin/mkdir
```

> Пути к бинарям уточните на своём сервере: `command -v rsync mkdir`
> (иногда `mkdir` лежит в `/usr/bin/mkdir`).

Проверка:

```bash
sudo -n rsync --version >/dev/null && echo OK
```

### 2.4. Скачать образ

```bash
cd /home/userdwh/DWH_cluster/ch_kafka_af_superset
docker compose -f docker-compose_cluster.yml pull clickhouse-backup
```

---

## 3. Ручной запуск

```bash
cd /home/userdwh/DWH_cluster/ch_kafka_af_superset
./scripts/ch_weekly_backup.sh
```

Скрипт по шагам:
1. `clickhouse-backup create weekly_<UTC-время>` — снимок на ноде;
2. `rsync -a` **только нового** снимка в `/mnt/backup/.../clickhouse_backup/weekly_<...>/`
   (без `--delete`, через `sudo`);
3. проверка, что копия непустая (есть `metadata/`) — иначе снимок на ноде **не удаляется**;
4. `clickhouse-backup delete local weekly_<...>` — снимок удаляется на ноде;
5. ретеншн в `/mnt/backup`: остаётся `BACKUPS_TO_KEEP_ARCHIVE` последних `weekly_*`,
   старые удаляются.

Переменные окружения скрипта (можно переопределить):

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `CLICKHOUSE_LOCAL_BACKUP` | `/mnt/2tb/.../data/clickhouse01/backup` | локальные снимки на ноде |
| `BACKUP_ARCHIVE` | `/mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup` | архив на репозитории |
| `BACKUPS_TO_KEEP_ARCHIVE` | `4` | сколько снимков хранить в `/mnt/backup` |
| `BACKUP_SUDO` | `auto` | `auto` / `always` / `never` |

> Ретеншн ведётся **только в `/mnt/backup`**. На ноде после каждого запуска снимок удаляется,
> поэтому диск данных не забивается бэкапами. `rsync --delete` **не используется** — копируется
> лишь новый каталог, старые в архиве чистит сам скрипт.

---

## 4. Расписание (cron)

Ночь с субботы на воскресенье, например воскресенье 02:30 по времени сервера:

```cron
30 2 * * 0 /home/userdwh/DWH_cluster/ch_kafka_af_superset/scripts/ch_weekly_backup.sh >> /var/log/ch_weekly_backup.log 2>&1
```

Установить:

```bash
crontab -e
# вставить строку выше
crontab -l          # проверить
```

---

## 5. Проверка результата

Содержимое архива на репозитории (тут лежат все снимки):

```bash
sudo ls -la /mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup/
sudo du -sh /mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup/*
```

На ноде после успешного запуска снимков быть **не должно** (или только неудачные):

```bash
docker compose -f docker-compose_cluster.yml --profile backup run --rm clickhouse-backup list local
```

Лог последнего запуска:

```bash
tail -n 50 /var/log/ch_weekly_backup.log
```

---

## 6. Восстановление (restore)

> Restore перезаписывает данные. Выполнять осознанно, желательно на тестовом узле.

Снимки хранятся в `/mnt/backup`, а `clickhouse-backup restore` работает с **локальным**
каталогом на ноде. Поэтому нужный снимок сначала возвращаем на ноду, затем восстанавливаем:

```bash
NAME=weekly_2026-05-24T20-59-59
LOCAL=/mnt/2tb/DWH_cluster/ch_kafka_af_superset/data/clickhouse01/backup
ARCHIVE=/mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup

# 1. вернуть снимок из архива на ноду (с правами процесса clickhouse — UID из контейнера)
CH_UID=$(docker exec clickhouse01 stat -c '%u' /var/lib/clickhouse)
CH_GID=$(docker exec clickhouse01 stat -c '%g' /var/lib/clickhouse)
sudo mkdir -p "$LOCAL/$NAME"
sudo rsync -a --numeric-ids "$ARCHIVE/$NAME/" "$LOCAL/$NAME/"
sudo chown -R "${CH_UID}:${CH_GID}" "$LOCAL/$NAME"

# 2. восстановить
docker compose -f docker-compose_cluster.yml --profile backup run --rm \
  clickhouse-backup restore --rm "$NAME"
```

---

## 7. Типовые ошибки

| Симптом | Причина | Решение |
|---------|---------|---------|
| `invalid cross-device link` | `backup/` на другом томе, чем `store/`/`shadow/` | Один volume на данные; копия на `/mnt/backup` только через `rsync` |
| `GetInProgressMutations ... context canceled` | Следствие сбоя на другой таблице (обычно cross-device) | Найти первую строку `ERR` в логе и устранить её |
| `can't freeze table ... Operation not permitted` | Испорчены права на `store/` (`chown userdwh` / `chmod 777`) | Вернуть владельца UID/GID процесса clickhouse (см. 2.2) |
| `rsync ... Permission denied (13)` | `backup/` принадлежит UID clickhouse, `userdwh` не читает | `rsync` через `sudo` (см. 2.3) |
| `BACKUP_ALREADY_EXISTS` / имя занято | Повтор имени бэкапа | Имя формируется по UTC-времени, повтор маловероятен; удалить старый снимок |

Найти первую реальную ошибку в логе:

```bash
grep -E 'ERR|FTL|invalid cross-device|Operation not permitted' /var/log/ch_weekly_backup.log | head -20
```

---

## 8. Бэкап PostgreSQL

PostgreSQL работает в `docker-compose_af.yml` (контейнер `postgres`, суперюзер `postgres`,
базы `airflow` и `superset`). Бэкап делается скриптом `scripts/pg_weekly_backup.sh` через
`pg_dumpall` — **без изменения compose**, чтобы не задеть прод.

- `pg_dumpall` снимает **все базы + роли/пароли** одним файлом (полное восстановление кластера).
- Дамп сразу пишется в `/mnt/backup/.../postgres_backup/pg_all_<UTC>.sql.gz` (через `sudo`).
- Ротация: хранится `BACKUPS_TO_KEEP` последних файлов (по умолчанию 5).

### Переменные скрипта

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `PG_CONTAINER` | `postgres` | имя контейнера |
| `PG_USER` | `postgres` | суперпользователь |
| `PG_PASSWORD` | `postgres` | пароль (`PGPASSWORD`) |
| `BACKUP_ARCHIVE` | `/mnt/backup/DWH_cluster/ch_kafka_af_superset/postgres_backup` | каталог дампов |
| `BACKUPS_TO_KEEP` | `5` | сколько дампов хранить |
| `BACKUP_SUDO` | `auto` | `auto` / `always` / `never` |

### Ручной запуск

```bash
cd /home/userdwh/DWH_cluster/ch_kafka_af_superset
./scripts/pg_weekly_backup.sh
```

### Расписание (cron)

Через 15 минут после ClickHouse, воскресенье 02:45:

```cron
45 2 * * 0 /home/userdwh/DWH_cluster/ch_kafka_af_superset/scripts/pg_weekly_backup.sh >> /var/log/pg_weekly_backup.log 2>&1
```

Для cron без пароля добавить в `/etc/sudoers.d/ch-backup-rsync` бинарники (уточнить пути
через `command -v tee mkdir find`):

```text
userdwh ALL=(ALL) NOPASSWD: /usr/bin/tee, /bin/mkdir, /usr/bin/find, /bin/rm
```

### Проверка и восстановление

```bash
# список дампов
sudo ls -la /mnt/backup/DWH_cluster/ch_kafka_af_superset/postgres_backup/

# восстановление ВСЕГО кластера (перезапишет роли и базы!)
gunzip -c /mnt/backup/.../postgres_backup/pg_all_2026-05-24T20-59-59.sql.gz \
  | docker exec -i -e PGPASSWORD=postgres postgres psql -U postgres -d postgres
```

> `pg_dumpall` с `--clean --if-exists` в дампе уже содержит `DROP` перед `CREATE`,
> поэтому restore идемпотентен. Проверяйте восстановление на тестовом окружении.
