import zipfile
import pandas as pd
from deep_translator import GoogleTranslator  # pip install deep-translator Оффлайн-перевод не поддерживается, используем кеширование
from kafka import KafkaProducer
import json
import os
from functools import lru_cache
import math

# Кешируем переводы, чтобы не переводить одно и то же многократно
@lru_cache(maxsize=100)
def translate_text(text, source='ru', target='en'):
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception as e:
        print(f"Translation failed for '{text}': {str(e)}")
        return text.lower().replace(' ', '_')  # Fallback

def extract_zip_file(zip_path, extract_to='.'):
    """Извлекает файл из zip-архива."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        file_list = zip_ref.namelist()
        if not file_list:
            raise ValueError("ZIP архив пуст")
        
        extracted_file = file_list[0]
        zip_ref.extract(extracted_file, extract_to)
        return os.path.join(extract_to, extracted_file)

def translate_columns(df):
    """Автоматически переводит названия столбцов с русского на английский."""
    translated_columns = []
    for col in df.columns:
        # Специальные случаи для сложных названий
        if "ИНН" in col:
            translated = col.replace("ИНН", "INN")
        elif "ГТИН" in col or "GTIN" in col:
            translated = "gtin"
        else:
            translated = translate_text(col)
        
        # Дополнительная обработка
        translated = (translated.lower()
                     .replace(',', '')
                     .replace('.', '')
                     .replace(' ', '_')
                     .replace('-', '_')
                     .replace('__', '_'))
        translated_columns.append(translated)
    
    return translated_columns

def df_to_json_chunks(df, chunk_size=100):
    """Разбивает DataFrame на чанки в JSON формате."""
    chunks = []
    total_rows = len(df)
    num_chunks = math.ceil(total_rows / chunk_size)
    
    for i in range(num_chunks):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, total_rows)
        chunk = df.iloc[start_idx:end_idx]
        chunks.append(chunk.to_dict(orient='records'))
    
    return chunks

def send_chunks_to_kafka(chunks, topic, bootstrap_servers='localhost:9092'):
    """Отправляет чанки данных в Kafka."""
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        batch_size=16384,  # Увеличиваем размер батча для эффективности
        linger_ms=10       # Небольшая задержка для батчинга
    )
    
    try:
        for i, chunk in enumerate(chunks):
            # Отправляем весь чанк как одно сообщение
            future = producer.send(topic, value={'chunk_id': i, 'data': chunk})
            
            # Можно добавить обработку результата
            # future.add_callback(on_send_success).add_errback(on_send_error)
            
        producer.flush()
        return True
    
    except Exception as e:
        print(f"Failed to send data to Kafka: {str(e)}")
        return False
    finally:
        producer.close()

def process_pricing_report(zip_path, kafka_topic, chunk_size=100, extract_to='.'):
    """Основной процесс обработки отчета."""
    try:
        # 1. Извлечение файла
        csv_path = extract_zip_file(zip_path, extract_to)
        print(f"Файл извлечен: {csv_path}")
        
        # 2. Загрузка данных
        df = pd.read_csv(csv_path, encoding='utf-8')
        
        # 3. Перевод названий столбцов
        df.columns = translate_columns(df)
        print("Названия столбцов переведены")
        
        # 4. Разбивка на чанки
        chunks = df_to_json_chunks(df, chunk_size=chunk_size)
        print(f"Данные разбиты на {len(chunks)} чанков по {chunk_size} записей")
        
        # 5. Отправка в Kafka
        success = send_chunks_to_kafka(chunks, kafka_topic)
        if success:
            print(f"Успешно отправлено {len(chunks)} чанков в топик {kafka_topic}")
        else:
            print("Произошла ошибка при отправке данных")
        
        return success
        
    except Exception as e:
        print(f"Ошибка обработки: {str(e)}")
        raise

if __name__ == "__main__":
    # Пример использования
    process_pricing_report(
        zip_path="GENERAL_PRICING_REPORT_acf5ef37-1294-4e12-888c-1476f91ad018.zip",
        kafka_topic="pricing_reports_chunked",
        chunk_size=200,  # Размер чанка можно настроить
        extract_to="./extracted_files"
    )