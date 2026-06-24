#!/bin/bash

SOURCE="~/DWH_dags"
TARGET="~/DWH_cluster/ch_kafka_af_superset/airflow/dags"
EXCLUDE_ITEMS="
__pycache__
.git
"
# Функция синхронизации
sync_data() {
    local rsync_cmd="rsync -avhP --delete"
    
    # Обрабатываем исключения (игнорируем пустые строки)
    while IFS= read -r exclude; do
        if [[ -n "$exclude" ]]; then
            rsync_cmd="$rsync_cmd --exclude='$exclude'"
        fi
    done <<< "$EXCLUDE_ITEMS"
    
    rsync_cmd="$rsync_cmd $SOURCE/ $TARGET/"
    
    echo "$(date): Запуск синхронизации"
    echo "Команда: $rsync_cmd"
    
    eval $rsync_cmd 2>&1
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "$(date): Синхронизация успешно завершена"
    else
        echo "$(date): Ошибка синхронизации"
    fi
}

# Проверка прав
if [ "$EUID" -eq 0 ]; then
    echo "Запуск с правами root"
else
    echo "Внимание: скрипт запущен без прав root"
fi

sync_data
