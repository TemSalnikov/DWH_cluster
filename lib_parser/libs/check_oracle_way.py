from datetime import datetime
execution_date = datetime.now()
print(execution_date)



        """
        WITH 
        ch_data as (
            select * from stg.mart_dcm_data on cluster cluster_2S_2R where deleted_flag = 0
        ),
        oracle_data as (
            SELECT * from DATA_MART."V$ALTAY_DATA"
        )
        /* Удаление отсутствующих строк на источнике БД Oracle */
        select ch_data.*
                , now() AS effective_dttm
                , 1 AS deleted_flag
        from ch_data
        left join oracle_data using(sales_type_id, cd_reg, cd_u, stat_year, stat_month)
        where oracle_data.sales_type_id is null
        union
        /* Добавление новых строк из источника БД Oracle */
        select oracle_data.*
                , current_date AS effective_dttm
                , 0 AS deleted_flag
        from oracle_data
        left join ch_data using(sales_type_id, cd_reg, cd_u, stat_year, stat_month)
        where ch_data.sales_type_id is null
        """


"""
    @task
    def load_altay_dict():
        """Загрузка и версионирование данных из V$ALTAY_DICT"""
        oracle_query = """
        SELECT 
            id, 
            name, 
            description,
            SYSTIMESTAMP AS effective_dttm,
            0 AS deleted_flag
        FROM DATA_MART.V$ALTAY_DICT
        """
        
        try:
            with get_oracle_connection() as oracle_conn:
                df_source = pd.read_sql(oracle_query, oracle_conn)
            
            ch_client = get_clickhouse_client()
            
            # Получаем существующие ID из ClickHouse
            existing_ids_result = ch_client.execute("SELECT id FROM altay_dict WHERE deleted_flag = 0")
            existing_ids = {row[0] for row in existing_ids_result} if existing_ids_result else set()
            
            # Находим новые и удаленные записи
            source_ids = set(df_source['id'])
            new_ids = source_ids - existing_ids
            deleted_ids = existing_ids - source_ids
            
            # Вставка новых записей
            if new_ids:
                df_new = df_source[df_source['id'].isin(new_ids)]
                ch_client.execute('INSERT INTO altay_dict VALUES', df_new.to_dict('records'))
                print(f"Добавлено {len(df_new)} новых записей в altay_dict")
            
            # Помечаем удаленные записи
            if deleted_ids:
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                update_query = f"""
                ALTER TABLE altay_dict
                UPDATE 
                    effective_dttm = '{current_time}',
                    deleted_flag = 1
                WHERE id IN ({','.join(map(str, deleted_ids))}) AND deleted_flag = 0
                """
                ch_client.execute(update_query)
                print(f"Помечено как удаленных {len(deleted_ids)} записей в altay_dict")
            
            if not new_ids and not deleted_ids:
                print("Нет изменений в altay_dict")
                
            ch_client.disconnect()
            
        except Exception as e:
            print(f"Ошибка при загрузке altay_dict: {str(e)}")
            raise
    
    @task
    def load_altay_reg():
        """Одноразовая загрузка данных из V$ALTAY_REG"""
        oracle_query = """
        SELECT 
            region_id,
            region_name,
            SYSTIMESTAMP AS effective_dttm,
            0 AS deleted_flag
        FROM DATA_MART.V$ALTAY_REG
        """
        
        try:
            with get_oracle_connection() as oracle_conn:
                df = pd.read_sql(oracle_query, oracle_conn)
            
            if not df.empty:
                ch_client = get_clickhouse_client()
                
                # Очищаем таблицу перед загрузкой (одноразовая полная загрузка)
                ch_client.execute("TRUNCATE TABLE altay_reg")
                
                # Вставляем новые данные
                ch_client.execute('INSERT INTO altay_reg VALUES', df.to_dict('records'))
                ch_client.disconnect()
                print(f"Успешно загружено {len(df)} записей в altay_reg")
            else:
                print("Нет данных для загрузки в altay_reg")
                
        except Exception as e:
            print(f"Ошибка при загрузке altay_reg: {str(e)}")
            raise
    
    # Определение порядка выполнения задач
    data_task = load_altay_data()
    dict_task = load_altay_dict()
    reg_task = load_altay_reg()
    
    # Параллельное выполнение всех задач
    data_task >> [dict_task, reg_task]

# Создание DAG
dag = altay_data_import_dag()

"""