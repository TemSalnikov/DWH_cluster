# Export Service — как пользоваться

Сервис выгружает данные дашбордов Superset в CSV **без лимита 100 000 строк**.

Данные берутся из ClickHouse. В Superset вы только смотрите, какие фильтры и чарты нужны — сами файлы качаются через этот сервис (Swagger или bash).

Уже подключен пример: дашборд **«Выбытия АС»**.

| Что | Значение |
|-----|----------|
| Адрес сервиса | http://localhost:8099 |
| **Пользовательский интерфейс** | **http://localhost:8099/** |
| Swagger (для админов) | http://localhost:8099/docs |
| Id в сервисе | `vybytiya_as` |
| Дашборд в Superset | http://192.168.14.226:8088 → «Выбытия АС» |

## Как выгрузить за 1 минуту (для любого пользователя)

1. Откройте http://localhost:8099/
2. Нажмите на отчёт (например «Выбытия АС»)
3. При необходимости поправьте период и фильтры → **Далее**
4. Выберите «Все строки» или нужную сводку → **Далее: показать данные**
5. Проверьте таблицу-образец → нажмите **Скачать полный файл**

Инструкция ниже — для запуска сервиса и подключения новых отчётов администратором.

---

# Часть 1. Запуск сервиса (один раз)

```bash
cd /path/to/ch_kafka_af_superset

cp export_service/.env.example export_service/.env
# при необходимости поправьте SUPERSET_URL и CLICKHOUSE_* в .env

docker compose -f export_service/docker-compose.yml up -d --build
```

Проверка:

```bash
curl http://localhost:8099/health
# ожидаете: {"status":"ok","dry_run":"false"}
```

Откройте в браузере: http://localhost:8099/docs

---

# Часть 2. Выгрузить данные — пример «Выбытия АС»

Ниже один и тот же сценарий тремя способами. Сначала разберитесь «что выбираем», потом повторите в Swagger или bash.

## 2.1. Что сделать в Superset (только чтобы понять фильтры)

1. Откройте дашборд **«Выбытия АС»**.
2. Посмотрите, какими фильтрами вы обычно ограничиваете данные, например:
   - период дат;
   - аптечная сеть;
   - регион;
   - тип выбытия.
3. Запомните значения, которые хотите выгрузить  
   (например период `2026-01-01` … `2026-03-31`, сеть `АСНА ПАС`).

**В самом дашборде ничего нажимать для выгрузки не нужно.**  
Кнопка CSV в Superset как раз ограничена 100k строк — её мы не используем.

В сервисе те же фильтры задаются в запросе (см. ниже).

## 2.2. Что выбрать в сервисе

| Параметр | Пример | Откуда взять |
|----------|--------|--------------|
| Дашборд | `vybytiya_as` | `GET /dashboards` |
| Тип выгрузки | `raw` = все строки таблицы; `top_points` = как чарт «Топ точек продаж»; `bundle_tables` = ZIP нескольких выгрузок | блок `exports` в ответе `/dashboards` |
| Фильтры | дата, owner, region… | `GET /dashboards/vybytiya_as/filters` |

## 2.3. Выгрузка через Swagger (самый простой путь)

1. Откройте http://localhost:8099/docs
2. Раскройте **`GET /dashboards`** → **Try it out** → **Execute**  
   Убедитесь, что в списке есть `vybytiya_as`.
3. (Опционально) **`GET /dashboards/{dashboard_id}/filters`**  
   - `dashboard_id` = `vybytiya_as`  
   - Execute — увидите доступные фильтры и списки значений.
4. Раскройте **`POST /exports`** → **Try it out**.  
   Вставьте тело:

```json
{
  "dashboard_id": "vybytiya_as",
  "export_id": "raw",
  "filters": {
    "date": { "from": "2026-01-01", "to": "2026-03-31" },
    "owner": ["АСНА ПАС"]
  }
}
```

5. **Execute**. В ответе будет примерно:

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "done",
  "file_name": "vybytiya_as_raw_20260912T120000Z.csv",
  ...
}
```

6. Скопируйте `job_id`.
7. Раскройте **`GET /exports/{job_id}/download`** → вставьте `job_id` → **Execute** → скачайте файл.

Другие варианты `export_id` для этого дашборда:

| export_id | Что получите |
|-----------|----------------|
| `raw` | Все строки `bdm.disposal_all_stats_2_ac` с фильтрами |
| `top_points` | Агрегат как чарт «Топ точек продаж» |
| `top_products` | Топ продуктов |
| `top_regions` | Топ регионов |
| `pivot_svod` | Свод по дате и продукту |
| `bundle_tables` | ZIP со всеми перечисленными CSV |

Перед реальной выгрузкой можно проверить SQL без скачивания файла:  
**`POST /exports/preview-sql`** — то же тело, что у `/exports`.

## 2.4. Выгрузка через bash

```bash
# 1) список дашбордов
curl -s http://localhost:8099/dashboards | python3 -m json.tool

# 2) создать выгрузку
curl -s -X POST http://localhost:8099/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "dashboard_id": "vybytiya_as",
    "export_id": "raw",
    "filters": {
      "date": {"from": "2026-01-01", "to": "2026-03-31"},
      "owner": ["АСНА ПАС"]
    }
  }' | tee /tmp/export_job.json | python3 -m json.tool

# 3) достать job_id и скачать файл
JOB=$(python3 -c "import json; print(json.load(open('/tmp/export_job.json'))['job_id'])")
curl -OJ "http://localhost:8099/exports/${JOB}/download"
# файл появится в текущей папке
```

Файл также лежит на сервере:

`export_service/data/exports/`

## 2.5. Как писать фильтры

Имена фильтров берутся из манифеста (`id`), не из подписей в Superset.

Для `vybytiya_as`:

```json
{
  "date": { "from": "2026-01-01", "to": "2026-03-31" },
  "owner": ["АСНА ПАС", "Ригла"],
  "region": ["Москва"],
  "disposal_type": ["Розничная продажа"],
  "product": ["Название продукта"]
}
```

Можно указать только нужные поля. Пустой объект `"filters": {}` — выгрузка с дефолтами из манифеста (для даты по умолчанию — текущий год).

Короткая запись периода:

```json
"date": "relative:current_year"
```

---

# Часть 3. Добавить новый дашборд (пример)

Допустим, нужно подключить дашборд **«Закупки АС»**.

## Шаг 1. Узнать id дашборда в Superset

1. Откройте дашборд в браузере.
2. В адресе будет что-то вроде `/superset/dashboard/20/` → id = **20**.  
   Либо смотрите список дашбордов в UI.

## Шаг 2. Сгенерировать черновик манифеста

```bash
docker exec -it export-service \
  python scripts/sync_dashboard.py --dashboard-id 20 --out manifests/zakupki_as.yaml
```

На хосте появится файл:

`export_service/manifests/zakupki_as.yaml`

Перезапускать контейнер **не нужно** — сервис читает YAML при каждом запросе.

## Шаг 3. Поправить манифест вручную

Откройте YAML и проверьте минимум:

1. `id:` — латиницей, без пробелов (например `zakupki_as`) — это то, что потом пишете в `dashboard_id` в Swagger.
2. `source.table:` — правильная таблица ClickHouse (например `bdm.ac_movement`).
3. `filters:` — какие фильтры нужны пользователю (дата, сети…).  
   Сверяйте с фильтрами на дашборде в Superset: колонка в CH = `column:` в YAML.
4. `exports:` — что можно скачивать:
   - оставьте `raw` (все строки);
   - для нужных табличных чартов поправьте `metrics` (после sync там часто бывает `TODO` — замените на реальный SQL из Explore → **View query**);
   - в `bundle_tables.include` перечислите id выгрузок для ZIP.

Кусок «как в Superset → как в YAML»:

| В дашборде Superset | В манифесте |
|---------------------|-------------|
| Фильтр «Период» по колонке `date_of_disposal` | `filters` → `id: date`, `column: date_of_disposal`, `type: date_range` |
| Фильтр «Аптечная сеть» по `owner` | `filters` → `id: owner`, `type: multi_select` |
| На всех чартах стоит «тип ≠ Остаток» | `defaults.where` |
| Чарт «Топ точек» (таблица) | `exports` с `mode: aggregate`, `group_by`, `metrics` |

Ориентир — готовый файл `manifests/vybytiya_as.yaml`.

## Шаг 4. Проверить, что дашборд появился

Swagger → `GET /dashboards` → Execute  
или:

```bash
curl -s http://localhost:8099/dashboards | python3 -m json.tool
```

Должен появиться новый `id` (например `zakupki_as`).

## Шаг 5. Выгрузить

Как в части 2, только подставьте новый id:

```json
{
  "dashboard_id": "zakupki_as",
  "export_id": "raw",
  "filters": {
    "date": { "from": "2026-01-01", "to": "2026-03-31" }
  }
}
```

В Swagger: **`POST /exports`** → затем **`GET /exports/{job_id}/download`**.

---

# Часть 4. Добавить один чарт к уже существующему дашборду

Пример: в «Выбытия АС» уже есть выгрузки, нужно добавить ещё одну «как чарт Топ АС».

1. В Superset откройте чарт → меню → **View query** (или Explore → три точки → View query).
2. Скопируйте смысл запроса: какие колонки в `GROUP BY`, какая метрика (`sum(total_volume)` и т.п.), какие постоянные условия.
3. В `manifests/vybytiya_as.yaml` в блок `exports:` добавьте:

```yaml
  - id: top_as
    label: "Топ АС"
    mode: aggregate
    group_by:
      - owner
    metrics:
      - label: "Объем, уп."
        expr: "sum(`total_volume`)"
    order_by:
      - "`Объем, уп.` DESC"
```

4. Если нужен этот чарт в ZIP — добавьте `top_as` в `bundle_tables.include`.
5. Сохраните файл.
6. Выгрузка:

```json
{
  "dashboard_id": "vybytiya_as",
  "export_id": "top_as",
  "filters": {
    "date": { "from": "2026-01-01", "to": "2026-03-31" }
  }
}
```

---

# Часть 5. Краткая шпаргалка

| Задача | Куда идти | Что сделать |
|--------|-----------|-------------|
| Запустить сервис | bash | `docker compose -f export_service/docker-compose.yml up -d --build` |
| Понять фильтры | Superset | Открыть дашборд, запомнить период и значения фильтров |
| Выгрузить файл | Swagger `/docs` | `POST /exports` → взять `job_id` → `GET /exports/{job_id}/download` |
| То же без браузера | bash | `curl …/exports` затем `curl -OJ …/download` |
| Добавить дашборд | bash + YAML | `sync_dashboard.py --dashboard-id N` → поправить YAML → `POST /exports` |
| Добавить чарт | YAML | Новый блок в `exports:` по View query из Superset |

---

# Часть 6. Если что-то не работает

| Симптом | Что проверить |
|---------|----------------|
| `curl: Connection refused` | Контейнер запущен? `docker ps \| grep export` |
| `status: failed` в ответе `/exports` | `docker logs export-service` — часто нет доступа к ClickHouse или ошибка в SQL манифеста |
| Дашборда нет в `/dashboards` | Есть ли файл в `export_service/manifests/*.yaml`, поле `id:` без опечатки |
| Пустой/не тот результат | Сверьте фильтры с дашбордом; проверьте SQL через `POST /exports/preview-sql` |
| Нужна отладка без ClickHouse | В `.env` поставьте `DRY_RUN=true`, пересоздайте контейнер — в файл запишется SQL |

Пересоздать контейнер после смены `.env`:

```bash
docker compose -f export_service/docker-compose.yml up -d --force-recreate
```
