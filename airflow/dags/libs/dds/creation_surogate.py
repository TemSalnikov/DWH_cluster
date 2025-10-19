import uuid
import logging
from typing import Dict, List
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickhouseError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


CLICKHOUSE_CONFIG = {
    'host': 'localhost',
    'port': 9000,
    'user': 'default',
    'password': '',
    'database': 'default'
}

def get_clickhouse_client():
    """Создание клиента ClickHouse"""
    try:
        client = Client(**CLICKHOUSE_CONFIG)
        logger.info("Успешное подключение к ClickHouse")
        return client
    except ClickhouseError as e:
        logger.error(f"Ошибка подключения к ClickHouse: {e}")
        raise

def get_last_load_data(source_table: str) -> str:
    """Получение последних данных из источника"""
    client = None
    tmp_table_name = f"tmp.tmp_{source_table}_{uuid.uuid4().hex}"
    
    try:
        client = get_clickhouse_client()
        logger.info(f"Начало получения данных из таблицы {source_table}")
        ### надо подусать над запросом
        query = f"""
        CREATE TABLE {tmp_table_name} AS 
        SELECT 
            product_id,
            src
        FROM stg.v_sv_all_{source_table}
        """
        
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

def compare_with_hub(tmp_table: str, hub_table: str) -> Dict[str, str]:
    """Сравнение данных с хаб-таблицей"""
    client = None
    in_hub_table = f"tmp.tmp_id_inhub_{uuid.uuid4().hex}"
    not_in_hub_table = f"tmp.tmp_id_notinhub_{uuid.uuid4().hex}"
    
    try:
        client = get_clickhouse_client()
        logger.info(f"Начало сравнения данных из {tmp_table} с хабом {hub_table}")
        
        # Данные присутствующие в hub
        query_in_hub = f"""
        CREATE TABLE {in_hub_table} AS
        SELECT DISTINCT 
            t.product_id,
            t.src
        FROM {tmp_table} t
        LEFT JOIN {hub_table} h 
            ON t.product_id = h.product_id AND t.src = h.src
        WHERE h.product_uuid IS NOT NULL
        """
        
        # Данные отсутствующие в hub
        query_not_in_hub = f"""
        CREATE TABLE {not_in_hub_table} AS
        SELECT DISTINCT 
            t.product_id,
            t.src
        FROM {tmp_table} t
        LEFT JOIN {hub_table} h 
            ON t.product_id = h.product_id AND t.src = h.src
        WHERE h.product_uuid IS NULL
        """
        
        client.execute(query_in_hub)
        logger.info(f"Создана таблица существующих записей: {in_hub_table}")
        
        client.execute(query_not_in_hub)
        logger.info(f"Создана таблица новых записей: {not_in_hub_table}")
        
        # Получим статистику
        count_in_hub = client.execute(f"SELECT count() FROM {in_hub_table}")[0][0]
        count_not_in_hub = client.execute(f"SELECT count() FROM {not_in_hub_table}")[0][0]
        
        logger.info(f"Статистика сравнения: {count_in_hub} записей в hub, {count_not_in_hub} новых записей")
        
        return {
            'in_hub': in_hub_table,
            'not_in_hub': not_in_hub_table
        }
        
    except ClickhouseError as e:
        logger.error(f"Ошибка при сравнении с хабом: {e}")
        raise
    finally:
        if client:
            client.disconnect()
            logger.debug("Подключение к ClickHouse закрыто")

def generate_uuids(tmp_table: str) -> str:
    """Генерация UUID для новых записей"""
    client = None
    pre_hub_table = f"tmp.pre_hub_{uuid.uuid4().hex}"
    
    try:
        client = get_clickhouse_client()
        logger.info(f"Генерация UUID для данных из {tmp_table}")
        
        query = f"""
        CREATE TABLE {pre_hub_table} AS
        SELECT 
            generateUUIDv4() as product_uuid,
            product_id,
            src
        FROM {tmp_table}
        """
        
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

def insert_to_hub(pre_hub_table: str, hub_table: str):
    """Вставка данных в хаб-таблицу"""
    client = None
    
    try:
        client = get_clickhouse_client()
        logger.info(f"Вставка данных из {pre_hub_table} в хаб {hub_table}")
        
        # Получим количество записей для вставки
        count_query = f"SELECT count() FROM {pre_hub_table}"
        count = client.execute(count_query)[0][0]
        
        query = f"""
        INSERT INTO {hub_table} (product_uuid, product_id, src)
        SELECT 
            product_uuid,
            product_id,
            src
        FROM {pre_hub_table}
        """
        
        client.execute(query)
        logger.info(f"Успешно вставлено {count} записей в таблицу {hub_table}")
        
    except ClickhouseError as e:
        logger.error(f"Ошибка при вставке в хаб: {e}")
        raise
    finally:
        if client:
            client.disconnect()
            logger.debug("Подключение к ClickHouse закрыто")

def cleanup_tables(table_names: List[str]):
    """Удаление временных таблиц"""
    if not table_names:
        logger.info("Нет временных таблиц для очистки")
        return
        
    client = None
    
    try:
        client = get_clickhouse_client()
        logger.info(f"Начало очистки {len(table_names)} временных таблиц")
        
        for table in table_names:
            if table and table.startswith(('tmp_', 'pre_hub_')):
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