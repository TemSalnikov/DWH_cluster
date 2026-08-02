# Бэкап ClickHouse (clickhouse01)

Еженедельный бэкап единственного рабочего узла ClickHouse из `docker-compose_cluster.yml`
средствами [`altinity/clickhouse-backup`](https://github.com/Altinity/clickhouse-backup).

- Снимок создаётся **локально** в каталоге данных ClickHouse: `.../data/clickhouse01/backup/`.
- Затем **копируется на репозиторий** `/mnt/backup` через `rsync`.
- Расписание — ночь с субботы на воскресенье (cron).

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
  backups_to_keep_local: 5         # хранить 5 последних локальных бэкапов
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

Скрипт:
1. `docker compose --profile backup run --rm clickhouse-backup create weekly_<UTC-время>`;
2. `rsync -a --delete` из локального `backup/` в `/mnt/backup/.../clickhouse_backup/`
   (через `sudo`, если у `userdwh` нет прав чтения).

Переменные окружения скрипта (можно переопределить):

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `CLICKHOUSE_LOCAL_BACKUP` | `/mnt/2tb/.../data/clickhouse01/backup` | локальные снимки |
| `BACKUP_ARCHIVE` | `/mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup` | зеркало на репозитории |
| `BACKUP_RSYNC_USE_SUDO` | `auto` | `auto` / `always` / `never` |

> `BACKUP_ARCHIVE` — это подкаталог `clickhouse_backup` внутри
> `/mnt/backup/DWH_cluster/ch_kafka_af_superset`. Отдельный подкаталог обязателен, потому что
> `rsync --delete` **полностью очищает приёмник** от всего, чего нет в источнике: нельзя
> направлять его прямо в `.../ch_kafka_af_superset`, иначе удалятся соседние данные.

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

Список локальных бэкапов:

```bash
docker compose -f docker-compose_cluster.yml --profile backup run --rm clickhouse-backup list local
```

Содержимое зеркала на репозитории:

```bash
sudo ls -la /mnt/backup/DWH_cluster/ch_kafka_af_superset/clickhouse_backup/
```

Лог последнего запуска:

```bash
tail -n 50 /var/log/ch_weekly_backup.log
```

---

## 6. Восстановление (restore)

> Restore перезаписывает данные. Выполнять осознанно, желательно на тестовом узле.

Список доступных бэкапов и восстановление конкретного:

```bash
docker compose -f docker-compose_cluster.yml --profile backup run --rm clickhouse-backup list local

docker compose -f docker-compose_cluster.yml --profile backup run --rm \
  clickhouse-backup restore --rm weekly_2026-05-24T20-59-59
```

Если бэкап есть только на `/mnt/backup`, сначала вернуть каталог снимка в локальный
`.../data/clickhouse01/backup/` (тем же `rsync` в обратную сторону, с правами clickhouse),
затем выполнить `restore`.

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
