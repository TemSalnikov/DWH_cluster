import json
from kafka import KafkaProducer
from kafka.errors import KafkaError
from airflow.utils.log.logging_mixin import LoggingMixin
from extract_from_remain_366 import transform_xl_to_json
import asyncio
import pandas as pd
import math

def create_producer(bootstrap_servers, max_request_size = 10485760):
    loger = LoggingMixin().log
    try:
        return KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            max_request_size = max_request_size,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            compression_type='gzip',
            retries=5,
            acks='all'
        )
    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

def send_message(producer, topic, message):
    loger = LoggingMixin().log
    try:
        future = producer.send(topic, value=message)
        record_metadata = future.get(timeout=10)  # блокировка до получения подтверждения
        loger.info(f"Message sent to {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")
    except KafkaError as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

def _estimate_size(df: pd.DataFrame) -> int:
        # """Оценивает размер датафрейма в байтах после сериализации в JSON"""
        sample = df.head(10).to_dict(orient='records')
        sample_size = len(json.dumps(sample).encode('utf-8'))
        estimated_size = sample_size * (len(df) / 10)
        return estimated_size

def _split_dataframe(df: pd.DataFrame, chunk_size: int) -> list:
        # """Разделяет датафрейм на части по количеству строк"""
        num_chunks = math.ceil(len(df) / chunk_size)
        return [df[i*chunk_size:(i+1)*chunk_size] for i in range(num_chunks)]
    
def send_dataframe(producer, topic, df, max_message_size = 1048576):
    # """
    # Отправляет датафрейм в Kafka, при необходимости разбивая на части
    
    # :param df: датафрейм для отправки
    # :param metadata: дополнительные метаданные для включения в сообщение
    # """
    loger = LoggingMixin().log
    
    # if metadata is None:
    #     metadata = {}
    
    # Оцениваем размер датафрейма
    estimated_size = _estimate_size(df)
    
    if estimated_size <= max_message_size:
        # Если датафрейм маленький, отправляем целиком
        message =  df.to_dict(orient='list')
        send_message(producer, topic, message)
        loger.info(f"Отправлен датафрейм целиком ({estimated_size} bytes) в топик {topic}")
    else:
        # Если датафрейм большой, разбиваем на части
        avg_row_size = estimated_size / len(df)
        chunk_size = max(1, int(max_message_size * 0.8 / avg_row_size))
        chunks = _split_dataframe(df, chunk_size)
        total_parts = len(chunks)
        
        loger.info(f"Разбиваю датафрейм на {total_parts} частей")
        
        for i, chunk in enumerate(chunks, 1):
            message =  chunk.to_dict(orient='list')
            send_message(producer, topic, message)
            loger.info(f"Отправлена часть {i}/{total_parts} (~{_estimate_size(chunk)} bytes) в топик {topic}")

async def background_sender(producer: KafkaProducer,  data_full: dict, prefix_topic = '', table_name = ''):
    loger = LoggingMixin().log
    try:
        topic = prefix_topic+'_'+table_name
        for _, data in data_full[table_name].iterrows():
            message = data.to_json().encode("utf-8")
            send_message(producer, topic, message)
        loger.info(f'Успешно записано в топик {topic} Kafka кластер {data_full[table_name][data_full[table_name].columns[0]].count()} строк!')
    except KafkaError as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

async def call_async_producer():
    loger = LoggingMixin().log
    bootstrap_servers = ['192.168.14.235:9091', '192.168.14.235:9092', '192.168.14.235:9093']
    prefix_topic = 'fpc_366'
    data_full = transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/остатки/2024/12_2024.xlsx', 
                                  sheet_name = 'Sheet1', 
                                  name_report = 'Остатки', 
                                  name_pharm_chain = '36.6')
    producer = create_producer(bootstrap_servers, max_request_size = 10485760)


    send_dataframe(producer, topic = prefix_topic+'_'+'table_drugstor', df = data_full['table_drugstor'])
    send_dataframe(producer, topic = prefix_topic+'_'+'table_product', df = data_full['table_product'])
    send_dataframe(producer, topic = prefix_topic+'_'+'table_report', df = data_full['table_report'])
    loger.info(f'Загрузка всех данных успешно завершена!')
    producer.close()

def call_producer(path):
    loger = LoggingMixin().log
    bootstrap_servers = ['kafka1:9091', 'kafak2:9092', 'kafka3:9093']
    prefix_topic = 'fpc_366'
    data_full = transform_xl_to_json(path, sheet_name = 'Sheet1', 
                                  name_report = 'Остатки', 
                                  name_pharm_chain = '36.6')
    producer = create_producer(bootstrap_servers, max_request_size = 10485760)


    send_dataframe(producer, topic = prefix_topic+'_'+'table_drugstor', df = data_full['table_drugstor'])
    send_dataframe(producer, topic = prefix_topic+'_'+'table_product', df = data_full['table_product'])
    send_dataframe(producer, topic = prefix_topic+'_'+'table_report', df = data_full['table_report'])
    loger.info(f'Загрузка всех данных успешно завершена!')
    producer.close()



if __name__ == "__main__":
    asyncio.run(call_async_producer())





    # loger = LoggingMixin().log
    # bootstrap_servers = ['192.168.14.235:9091', '192.168.14.235:9092', '192.168.14.235:9093']
    # topic = 'fpc_366'
    # data_full = transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx', 
    #                               sheet_name = 'Sheet1', 
    #                               name_report = 'Закупки', 
    #                               name_pharm_chain = '36.6')
    # producer = create_producer(bootstrap_servers, max_request_size = 10485760)

    # for _, data in data_full['table_drugstor'].iterrows():
    #     message = data.to_json().encode("utf-8")
    #     send_message(producer, topic+'_table_drugstor', message)
    # for _, data in data_full['table_suplier'].iterrows():
    #     message = data.to_json().encode("utf-8")
    #     send_message(producer, topic+'_table_suplier', message)
    # for _, data in data_full['table_product'].iterrows():
    #     message = data.to_json().encode("utf-8")
    #     send_message(producer, topic+'_table_product', message)
    # for _, data in data_full['table_report'].iterrows():
    #     message = data.to_json().encode("utf-8")
    #     send_message(producer, topic+'_table_report', message)
    
    # producer.close()


