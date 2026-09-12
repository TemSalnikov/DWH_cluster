# Export Service

Отдельный сервис полной выгрузки данных дашбордов Apache Superset **без лимита 100 000 строк**.

- **Данные** читаются напрямую из ClickHouse (стрим в CSV / ZIP).
- **Superset** используется только как источник метаданных (дашборды, чарты, фильтры) при подключении новых выгрузок.
- Связь «дашборд → таблица → фильтры → профили выгрузки» описывается YAML-манифестами — без правок Python на каждый дашборд.

Пример: дашборд **«Выбытия АС»** (`manifests/vybytiya_as.yaml`, Superset `dashboard_id=16`, таблица `bdm.disposal_all_stats_2_ac`).

---

## Содержание

1. [Архитектура и взаимодействие с Superset](#1-архитектура-и-взаимодействие-с-superset)
2. [Интерфейс системы (API)](#2-интерфейс-системы-api)
3. [Добавление выгрузок и перенос фильтров из Superset](#3-добавление-выгрузок-и-перенос-фильтров-из-superset)
4. [Инструкция по запуску (Docker)](#4-инструкция-по-запуску-docker)
5. [Локальный запуск без Docker](#5-локальный-запуск-без-docker)
6. [Структура каталога](#6-структура-каталога)

---

## 1. Архитектура и взаимодействие с Superset

### Роли компонентов

| Компонент | Роль |
|-----------|------|
| **Superset** | Витрина аналитики. Хранит дашборды, чарты, native/adhoc-фильтры, SQL-выражения метрик. **Не** используется для массовой выгрузки строк. |
| **Export Service** | UI/API выгрузки: принимает выбранный дашборд + значения фильтров, строит SQL по манифесту, стримит результат из ClickHouse. |
| **ClickHouse** | Источник данных (`bdm.*` и др.). Выгрузки идут read-only запросами. |
| **Манифесты YAML** | Контракт между дашбордом Superset и сервисом: таблица, фильтры, профили export. |

### Схема потоков

```
┌──────────────────┐  metadata only (login, charts, sync)
│ Apache Superset  │◄─────────────────────────────────────┐
│  dashboards/     │                                      │
│  charts/filters  │                                      │
└────────┬─────────┘                                      │
         │ пользователь смотрит дашборд                   │
         │ (как раньше)                                   │
         ▼                                                │
┌──────────────────┐     POST /exports                    │
│  Клиент / UI     │─────────────────────────────────────►│
│  (curl, Swagger, │◄── CSV / ZIP / status ───────────────┤
│   будущий фронт) │                                      │
└──────────────────┘                                      │
                                                          │
                              ┌───────────────────────────┴────────────┐
                              │           Export Service               │
                              │  ManifestRegistry  FilterCompiler      │
                              │  ExportWorker (jobs)  Superset sync    │
                              └───────────────┬────────────────────────┘
                                              │ SELECT … FORMAT/CSV stream
                                              ▼
                                      ┌───────────────┐
                                      │  ClickHouse   │
                                      │  bdm.*        │
                                      └───────────────┘
```

### Когда сервис ходит в Superset

| Сценарий | Ходит в Superset? | Ходит в ClickHouse? |
|----------|-------------------|---------------------|
| `GET /dashboards`, выгрузка по манифесту | Нет | Да (если не `DRY_RUN`) |
| `python scripts/sync_dashboard.py` | Да (чтение чартов) | Нет |
| Список значений фильтра (`values_from.distinct`) | Нет | Да (`SELECT DISTINCT`) |

Итого в рантайме выгрузки Superset **не участвует** — только ClickHouse + локальный YAML. Это снимает лимит `SQL_MAX_ROW=100000` и не нагружает gunicorn Superset тяжёлыми CSV.

### Учётные данные

В `.env`:

- `SUPERSET_URL` / `SUPERSET_USERNAME` / `SUPERSET_PASSWORD` — только для **sync** манифестов.
- `CLICKHOUSE_*` — для выгрузок и distinct-значений фильтров.

Рекомендуется отдельный read-only пользователь ClickHouse с лимитами `max_execution_time` / `max_result_bytes`.

---

## 2. Интерфейс системы (API)

Сервис — FastAPI. После запуска:

- API: `http://<host>:8099`
- Swagger UI: `http://<host>:8099/docs`
- OpenAPI JSON: `http://<host>:8099/openapi.json`

Отдельного веб-UI пока нет: взаимодействие через Swagger / `curl` / будущий фронтенд.

### Эндпоинты

| Method | Path | Описание |
|--------|------|----------|
| `GET` | `/health` | Liveness (`status`, флаг `dry_run`) |
| `GET` | `/dashboards` | Список подключённых дашбордов (из YAML) |
| `GET` | `/dashboards/{id}` | Полный манифест |
| `GET` | `/dashboards/{id}/filters` | Описание фильтров + `values` (distinct из CH) |
| `POST` | `/exports/preview-sql` | Собрать SQL **без** выполнения |
| `POST` | `/exports` | Создать выгрузку (синхронный job) |
| `GET` | `/exports/{job_id}` | Статус job |
| `GET` | `/exports/{job_id}/download` | Скачать CSV или ZIP |

`{id}` — это **id манифеста** (например `vybytiya_as`), не числовой id Superset.

### Типовой сценарий выгрузки

```bash
# 1. Какие дашборды подключены
curl -s http://localhost:8099/dashboards | python3 -m json.tool

# 2. Какие фильтры и какие значения доступны
curl -s http://localhost:8099/dashboards/vybytiya_as/filters | python3 -m json.tool

# 3. Превью SQL
curl -s -X POST http://localhost:8099/exports/preview-sql \
  -H 'Content-Type: application/json' \
  -d '{
    "dashboard_id": "vybytiya_as",
    "export_id": "top_points",
    "filters": {
      "date": {"from": "2026-01-01", "to": "2026-03-31"},
      "owner": ["АСНА ПАС"]
    }
  }' | python3 -m json.tool

# 4. Запуск выгрузки
curl -s -X POST http://localhost:8099/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "dashboard_id": "vybytiya_as",
    "export_id": "raw",
    "filters": {
      "date": "relative:current_year",
      "owner": ["АСНА ПАС"]
    }
  }' | python3 -m json.tool
# → {"job_id":"...", "status":"done", "file_name":"vybytiya_as_raw_....csv", ...}

# 5. Скачать файл
curl -OJ http://localhost:8099/exports/<job_id>/download
```

### Формат `filters` в запросе

Ключи = `id` фильтров из манифеста:

| Тип фильтра в YAML | Значение в JSON |
|--------------------|-----------------|
| `date_range` | `{"from":"YYYY-MM-DD","to":"YYYY-MM-DD"}` или `"relative:current_year"` / `current_month` / `last_30d` |
| `multi_select` | массив строк: `["Значение1", "Значение2"]` |
| `text` | одна строка |

Непереданные необязательные фильтры пропускаются (или берётся `default` из манифеста). Неизвестные ключи → `400`.

### Профили выгрузки (`exports`)

| `mode` | Результат |
|--------|-----------|
| `raw` | `SELECT` всех (или указанных) колонок таблицы с WHERE |
| `aggregate` | `GROUP BY` + метрики (аналог table/pivot чарта) |
| `bundle` | ZIP из нескольких профилей (`include: [...]`) |

Файлы сохраняются в `export_service/data/exports/` (том Docker → `/data/exports`).

---

## 3. Добавление выгрузок и перенос фильтров из Superset

Цель: новый дашборд за **минуты**, без изменения кода сервиса.

### 3.1. Автогенерация draft-манифеста

```bash
# из контейнера
docker exec -it export-service \
  python scripts/sync_dashboard.py --dashboard-id 16 --out manifests/vybytiya_as.yaml

# или локально (нужен доступ к SUPERSET_URL)
cd export_service
python scripts/sync_dashboard.py --dashboard-id 20 --out manifests/zakupki_as.yaml
```

Что делает `sync`:

1. Логин в Superset API (`/api/v1/security/login`).
2. Обход `/api/v1/chart/` и отбор чартов, у которых в `dashboards` есть нужный `dashboard_id`  
   (прямой `GET /api/v1/dashboard/{id}` у JWT часто отдаёт 404 — поэтому связь идёт через чарты).
3. Определение основной таблицы (`datasource_name_text`, напр. `bdm.disposal_all_stats_2_ac`).
4. Эвристика `defaults.where` из adhoc-фильтров, общих для большинства чартов  
   (для «Выбытия АС»: `type_of_disposal NOT IN ('Остаток')`).
5. Черновик UI-фильтров из частых `groupby` / временных колонок.
6. Профили `exports` для чартов `table` / `pivot_table_v2` + `raw` + `bundle`.

### 3.2. Ручная доводка манифеста (обязательно)

Откройте YAML и проверьте:

1. **`id` / `title`** — человекочитаемые.
2. **`source.table`** — схема.таблица ClickHouse.
3. **`defaults.where`** — «вшитые» условия дашборда (эквивалент постоянных adhoc-фильтров чартов).
4. **`filters`** — только те измерения, которыми пользователь крутит дашборд в Superset (дата, АС, регион, продукт…).
5. **`exports[].metrics[].expr`** — после sync могут быть `sum(\`TODO_...\`)`; подставьте реальные выражения из чарта (в Explore → View query или через `POST /api/v1/chart/data` с `result_type=query`).
6. **`bundle.include`** — список профилей в ZIP.

Манифесты монтируются в контейнер **read-only**; после сохранения файла на хосте `GET /dashboards` подхватывает изменения без ребилда (registry читает YAML на запрос).

### 3.3. Как переносить параметры фильтрации из Superset

В Superset фильтры живут в двух местах — оба нужно учесть в манифесте.

#### A. Native filters дашборда

В UI: Dashboard → фильтры сверху (период, АС, регион…).

В API (если доступен `GET /api/v1/dashboard/{id}`):  
`json_metadata.native_filter_configuration[]` → поля `name`, `targets[].column.name`, `filterType`.

В манифест это ложится так:

```yaml
filters:
  - id: date                    # стабильный ключ для API
    label: "Период"             # как в Superset
    column: date_of_disposal    # targets.column.name
    type: date_range
    default: "relative:current_year"
```

#### B. Adhoc-фильтры чартов

В Explore у чарта: `adhoc_filters` (например `type_of_disposal NOT IN ['Остаток']`).

- Если фильтр **общий для дашборда** и пользователь его не снимает → `defaults.where`.
- Если фильтр **выбираемый** → элемент `filters` с `type: multi_select` / `date_range`.

Пример переноса для «Выбытия АС»:

| В Superset | В манифесте |
|------------|-------------|
| Native / time: `date_of_disposal` | `filters.id: date`, `type: date_range` |
| Частый groupby / native: `owner` | `filters.id: owner`, `values_from.distinct: owner` |
| Adhoc на почти всех чартах: `type_of_disposal NOT IN ('Остаток')` | `defaults.where` |
| Table «Топ точек продаж»: groupby + SUM | `exports.id: top_points`, `mode: aggregate` |

#### C. Соответствие значений UI → SQL

`FilterCompiler` принимает только колонки из `filters` манифеста (allowlist) и собирает WHERE:

```text
defaults.where  AND  user filters  AND  export.extra_where
```

Пользователь **не может** подставить произвольный SQL — только значения для объявленных фильтров.

### 3.4. Чеклист нового дашборда

1. `sync_dashboard.py --dashboard-id <N> --out manifests/<slug>.yaml`
2. Поправить лейблы, `defaults`, метрики, bundle.
3. `curl /dashboards` — новый id виден.
4. `POST /exports/preview-sql` — SQL похож на View query в Superset.
5. `DRY_RUN=false` → `POST /exports` → скачать файл, сверить строки с чартом на тех же фильтрах.

---

## 4. Инструкция по запуску (Docker)

### Требования

- Docker + Docker Compose
- Сеть `click_network` и доступные сервисы `clickhouse01`, `superset` (или `superset2`)
- Файл `export_service/.env` (скопируйте из `.env.example`)

### 4.1. Настройка `.env`

```bash
cp export_service/.env.example export_service/.env
```

Важные переменные:

| Переменная | Пример в Docker | Назначение |
|------------|-----------------|------------|
| `SUPERSET_URL` | `http://superset:8088` | Sync манифестов (`superset2` в af-стеке) |
| `CLICKHOUSE_HOST` | `clickhouse01` | Выгрузки |
| `CLICKHOUSE_PORT` | `8123` | HTTP-порт CH |
| `DRY_RUN` | `false` | `true` — писать файл с SQL без запроса в CH |
| `EXPORT_SERVICE_PORT` | `8099` | Порт на хосте |

### 4.2. Вариант A — вместе с основным стеком

```bash
# из корня репозитория
docker compose -f docker-compose.yml up -d --build export-service

# или af-стек
docker compose -f docker-compose_af.yml up -d --build export-service
```

Сервис слушает **8099** на хосте, в сети — `http://export-service:8099`.

### 4.3. Вариант B — только export-service (overlay)

Если стек уже поднят и сеть `click_network` существует:

```bash
docker compose -f export_service/docker-compose.yml up -d --build
```

### 4.4. Проверка

```bash
docker ps --filter name=export-service
docker logs -f export-service

curl -s http://localhost:8099/health
curl -s http://localhost:8099/dashboards | python3 -m json.tool
```

Swagger: http://localhost:8099/docs

### 4.5. Обновление манифестов без ребилда

Файлы в `export_service/manifests/` смонтированы в контейнер. Достаточно отредактировать/добавить YAML на хосте — API сразу видит изменения.

Ребилд нужен только при изменении Python-кода / `requirements.txt`:

```bash
docker compose -f docker-compose.yml up -d --build export-service
```

### 4.6. Выгрузки на диске

Каталог хоста: `export_service/data/exports/`  
В контейнере: `/data/exports`

---

## 5. Локальный запуск без Docker

```bash
cd export_service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# для отладки SQL без CH:
# DRY_RUN=true
# SUPERSET_URL/CLICKHOUSE_* — укажите доступные с вашей машины хосты

uvicorn app.main:app --reload --port 8099
```

Sync с хоста:

```bash
python scripts/sync_dashboard.py --dashboard-id 16 --out manifests/vybytiya_as.yaml
```

---

## 6. Структура каталога

```
export_service/
  Dockerfile
  docker-compose.yml          # overlay на click_network
  requirements.txt
  .env.example
  README.md
  manifests/
    vybytiya_as.yaml          # пример: Выбытия АС
  data/exports/               # результаты выгрузок (volume)
  scripts/
    sync_dashboard.py         # draft YAML из Superset
  app/
    main.py                   # FastAPI
    config.py
    models.py                 # pydantic-схема манифеста и API
    registry.py               # загрузка YAML
    filters.py                # фильтры → WHERE / SQL
    clickhouse.py             # выполнение в CSV
    jobs.py                   # jobs + ZIP bundle
    sync.py                   # генерация draft
    superset_client.py        # read-only Superset API
```

В корне репозитория сервис также описан в:

- `docker-compose.yml` → service `export-service`
- `docker-compose_af.yml` → service `export-service` (по умолчанию `SUPERSET_URL=http://superset2:8088`)
