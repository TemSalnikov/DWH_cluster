import json
from kafka import KafkaProducer
from kafka.errors import KafkaError
from airflow.utils.log.logging_mixin import LoggingMixin
from extract_from_xl import transform_xl_to_json

def create_producer(bootstrap_servers):
    loger = LoggingMixin().log
    try:
        return KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            # value_serializer=lambda v: json.dumps(v).encode('utf-8'),
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
        print(f"Message sent to {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")
    except KafkaError as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

if __name__ == "__main__":
    bootstrap_servers = ['kafka1:9091', 'kafka2:9092', 'kafka3:9093']
    topic = 'my_sharded_topic'
    
    producer = create_producer(bootstrap_servers)
    
    # Пример JSON сообщения
    message = transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx', 
                                  sheet_name = 'Sheet1', 
                                  name_report = 'Закупки', 
                                  name_pharm_chain = '36.6')
    
    send_message(producer, topic, message)
    
    producer.close()