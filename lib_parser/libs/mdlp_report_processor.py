import os
import sys
import zipfile
import pandas as pd
import json
from datetime import datetime
from deep_translator import GoogleTranslator

# Добавляем путь к библиотекам
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))
from kafka_producer_common_for_xls import create_producer, send_dataframe

def translate_columns(columns):
    """Перевод названий столбцов с русского на английский"""
    translated = []
    for col in columns:
        if "ИНН" in col:
            translated.append(col.replace("ИНН", "INN"))
        elif "ГТИН" in col or "GTIN" in col:
            translated.append("gtin")
        else:
            try:
                # Пытаемся перевести
                trans = GoogleTranslator(source='ru', target='en').translate(col)
                # Нормализация названия столбца
                trans = (trans.lower()
                         .replace(',', '')
                         .replace('.', '')
                         .replace(' ', '_')
                         .replace('-', '_')
                         .replace('__', '_'))
                translated.append(trans)
            except:
                # Fallback: транслитерация
                translated.append(col)
    return translated

def process_report(zip_path, report_type, date_to):
    """Обработка отчёта: извлечение, преобразование и отправка в Kafka"""
    try:
        # Извлечение из архива
        extract_dir = "/tmp/extracted"
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            if not file_list:
                return {"status": "error", "message": "Empty ZIP archive"}
                
            csv_filename = file_list[0]
            zip_ref.extract(csv_filename, extract_dir)
            csv_path = os.path.join(extract_dir, csv_filename)
        
        # Чтение CSV
        df = pd.read_csv(csv_path, encoding='utf-8', sep=';')
        
        if df.empty:
            return {"status": "empty", "report_type": report_type, "date_to": date_to}
        
        # Добавление метаданных
        df['type_report'] = report_type
        df['date_to'] = date_to
        df['create_dttm'] = datetime.now()
        
        # Перевод названий столбцов
        df.columns = translate_columns(df.columns)
        
        # Отправка в Kafka
        bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka1:19092,kafka2:19092,kafka3:19092").split(',')
        producer = create_producer(bootstrap_servers)
        topic_name = f"mdlp_{report_type.lower()}"
        send_dataframe(producer, topic_name, df)
        producer.close()
        
        # Очистка
        os.remove(csv_path)
        os.remove(zip_path)
        
        return {"status": "success", "report_type": report_type, "date_to": date_to}
    
    except Exception as e:
        return {"status": "error", "message": str(e), "report_type": report_type, "date_to": date_to}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip-path', required=True)
    parser.add_argument('--report-type', required=True)
    parser.add_argument('--date-to', required=True)
    args = parser.parse_args()
    
    result = process_report(args.zip_path, args.report_type, args.date_to)
    print(json.dumps(result))