# import fn_creation_surogate
import uuid
from datetime import datetime
from airflow.decorators import dag, task_group, task
from airflow.utils.log.logging_mixin import LoggingMixin
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickhouseError

CLICKHOUSE_CONN: dict[str, str | int] = {
    'host': '192.168.14.235',
    'port': 9001,
    'user': 'admin',
    'password': 'admin',
}

def get_clickhouse_client():
    """Создание клиента ClickHouse"""
    logger = LoggingMixin().log
    try:
        return Client(
                host=CLICKHOUSE_CONN['host'],
                port=CLICKHOUSE_CONN['port'],
                user=CLICKHOUSE_CONN['user'],
                password=CLICKHOUSE_CONN['password']
            )
    except ClickhouseError as e:
        logger.error(f"Ошибка подключения к ClickHouse: {e}")
        raise 

@task_group(group_id = 'load_hub')
def hub_load_processing_tasks(hub_name: str, source_table: str, src_pk:str,  hub_pk: str, hub_id: str):
    
    @task
    def get_last_load_data(source_table: str) -> str:
        """Получение последних данных из источника"""
        client = None
        tmp_table_name = f"tmp.tmp_v_sv_all_{source_table}_{uuid.uuid4().hex}"
        logger = LoggingMixin().log
        try:
            client = get_clickhouse_client()
            logger.info(f"Подклчение к clickhouse успешно выполнено")
            ### надо подумать над запросом
            query = f"""
            CREATE TABLE {tmp_table_name} 
            ENGINE = MergeTree()
            PRIMARY KEY ({src_pk})
            ORDER BY ({src_pk})
            AS 
            SELECT 
                {src_pk},
                src,
                effective_dttm
            FROM stg.v_sv_all_{source_table}
            """
            logger.info(f"Создан запрос: {query}")

            client.execute(query)
            logger.info(f"Создана временная таблица {tmp_table_name} с данными из {source_table}")
            
            return tmp_table_name
            
        except ClickhouseError as e:
            logger.error(f"Ошибка при получении данных из {source_table}: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")
    
    @task
    def get_increment_load_data(source_table: str, p_from_proces_dttm: str, p_end_proces_dttm: str) -> str:
        """Получение последних данных из источника"""
        client = None
        tmp_table_name = f"tmp.tmp_v_si_all_{source_table}_{uuid.uuid4().hex}"
        logger = LoggingMixin().log
        try:
            client = get_clickhouse_client()
            logger.info(f"Подклчение к clickhouse успешно выполнено")
            ### надо подумать над запросом
            query = f"""
            CREATE TABLE {tmp_table_name} 
            ENGINE = MergeTree()
            PRIMARY KEY ({src_pk})
            ORDER BY ({src_pk})
            AS 
            SELECT 
                {src_pk},
                src,
                effective_dttm
            FROM stg.v_si_all_{source_table}({p_from_proces_dttm},{p_end_proces_dttm})
            FROM stg.v_sv_all_{source_table}
            """
            logger.info(f"Создан запрос: {query}")
            
            client.execute(query)
            logger.info(f"Создана временная таблица {tmp_table_name} с данными из {source_table}")
            
            return tmp_table_name
        except ClickhouseError as e:
            logger.error(f"Ошибка при получении данных из {source_table}: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")
    
    @task
    def compare_with_hub(tmp_table: str, hub_table: str) -> str:
        """Сравнение данных с хаб-таблицей"""
        client = None
        in_hub_table = f"tmp.tmp_id_inhub_{uuid.uuid4().hex}"
        not_in_hub_table = f"tmp.tmp_id_notinhub_{uuid.uuid4().hex}"
        logger = LoggingMixin().log
        try:
            client = get_clickhouse_client()
            logger.info(f"Начало сравнения данных из {tmp_table} с хабом {hub_table}")
            
            # Данные присутствующие в hub
            # query_in_hub = f"""
            # CREATE TABLE {in_hub_table} AS
            # SELECT DISTINCT 
            #     h.{name_sur_key},
            #     t.{pk},
            #     t.src,
            #     t.effective_dttm
            # FROM {tmp_table} t
            # LEFT JOIN dds.{hub_table} h 
            #     ON t.{pk} = h.{pk} AND t.src = h.src
            # WHERE h.{name_sur_key} IS NOT NULL
            # """
            query_set = "SET allow_experimental_join_condition = 1"
            client.execute(query_set)

            # Данные отсутствующие в hub
            query_not_in_hub = f"""
            CREATE TABLE {not_in_hub_table} 
            ENGINE = MergeTree()
            PRIMARY KEY ({src_pk})
            ORDER BY ({src_pk})
            AS
            SELECT DISTINCT 
                t.{src_pk},
                t.src,
                t.effective_dttm
            FROM {tmp_table} t
            LEFT JOIN {hub_table} h 
                ON t.{src_pk} = h.{hub_id} AND t.src = h.src AND h.effective_from_dttm <= t.effective_dttm
                AND h.effective_to_dttm > t.effective_dttm
            WHERE h.{hub_pk} = ''
            """
            logger.info(f"Создан запрос: {query_not_in_hub}")
            # client.execute(query_in_hub)
            # logger.info(f"Создана таблица существующих записей: {in_hub_table}")
            
            client.execute(query_not_in_hub)
            logger.info(f"Создана таблица новых записей: {not_in_hub_table}")
            
            # Получим статистику
            # count_in_hub = client.execute(f"SELECT count() FROM {in_hub_table}")[0][0]
            count_not_in_hub = client.execute(f"SELECT count() FROM {not_in_hub_table}")[0][0]
            logger.info(f"Новых id: {count_not_in_hub}")
            
            # logger.info(f"Статистика сравнения: {count_in_hub} записей в hub, {count_not_in_hub} новых записей")
            
            # return {
            #     'in_hub': in_hub_table,
            #     'not_in_hub': not_in_hub_table
            # }
            return not_in_hub_table
            
        except ClickhouseError as e:
            logger.error(f"Ошибка при сравнении с хабом: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")

    @task
    def generate_uuids(tmp_table: str) -> str:
        """Генерация UUID для новых записей"""
        client = None
        pre_hub_table = f"tmp.pre_hub_{uuid.uuid4().hex}"
        logger = LoggingMixin().log
        try:
            client = get_clickhouse_client()
            logger.info(f"Генерация UUID для данных из {tmp_table}")
            
            query = f"""
            CREATE TABLE {pre_hub_table} 
            ENGINE = MergeTree()
            PRIMARY KEY ({hub_pk})
            ORDER BY ({hub_pk})
            AS
            SELECT 
                toString(generateUUIDv4()) as {hub_pk},
                {src_pk} as {hub_id},
                src,
                effective_dttm
            FROM {tmp_table}
            WHERE {src_pk} != ''
            UNION ALL
            SELECT 
                '-1' as {hub_pk},
                {src_pk} as {hub_id},
                src,
                effective_dttm
            FROM {tmp_table}
            WHERE {src_pk} = ''
            """
            logger.info(f"Создан запрос: {query}")
            client.execute(query)
            
            # Получим количество сгенерированных записей
            count = client.execute(f"SELECT count() FROM {pre_hub_table}")[0][0]
            logger.info(f"Сгенерировано {count} UUID в таблице {pre_hub_table}")
            
            return pre_hub_table
            
        except ClickhouseError as e:
            logger.error(f"Ошибка при генерации UUID: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")

    @task
    def insert_to_hub(pre_hub_table: str, hub_table: str):
        """Вставка данных в хаб-таблицу"""
        client = None
        logger = LoggingMixin().log
        try:
            client = get_clickhouse_client()
            logger.info(f"Вставка данных из {pre_hub_table} в хаб {hub_table}")
            
            # Получим количество записей для вставки
            count_query = f"SELECT count() FROM {pre_hub_table}"
            count = client.execute(count_query)[0][0]
            processed_dttm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(processed_dttm)
            query = f"""
            INSERT INTO {hub_table}
            SELECT 
                {hub_pk},
                {hub_id},
                src,
                effective_dttm as effective_from_dttm,
                '2099-12-31 23:59:59' as effective_to_dttm,
                '{processed_dttm}' as processed_dttm,
                False as deleted_flg
            FROM {pre_hub_table}
            """
            logger.info(f"Создан запрос: {query}")
            client.execute(query)
            logger.info(f"Успешно вставлено {count} записей в таблицу {hub_table}")
            
        except ClickhouseError as e:
            logger.error(f"Ошибка при вставке в хаб: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")
    
    @task
    def cleanup_tables(*args, **kwargs):
        """Удаление временных таблиц"""
        logger = LoggingMixin().log
        if not args:
            logger.info("Нет временных таблиц для очистки")
            return
            
        client = None
        
        try:
            client = get_clickhouse_client()
            logger.info(f"Начало очистки {len(args)} временных таблиц")
            logger.info(args[0])
            for table in args[0]:
                if table and table.startswith('tmp.'):
                    try:
                        query = f"DROP TABLE IF EXISTS {table}"
                        client.execute(query)
                        logger.info(f"Таблица {table} успешно удалена")
                    except ClickhouseError as e:
                        logger.warning(f"Не удалось удалить таблицу {table}: {e}")
                else:
                    logger.warning(f"Пропущено удаление таблицы с неподходящим именем: {table}")
                    
            logger.info("Очистка временных таблиц завершена")
            
        except ClickhouseError as e:
            logger.error(f"Ошибка при очистке таблиц: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")

    # last_load_table = get_last_load_data(source_table = source_table) ### наверное эту временную таблицу нужно вне task group получать и передавать во внутрь
    cmp_table = compare_with_hub(tmp_table = source_table, hub_table = hub_name)
    uuid_table = generate_uuids(tmp_table=cmp_table)
    insert_to_hub = insert_to_hub(pre_hub_table = uuid_table, hub_table = hub_name)
    cleanup_tables = cleanup_tables([cmp_table, uuid_table])

    cmp_table >> uuid_table >> insert_to_hub >> cleanup_tables
    




    
