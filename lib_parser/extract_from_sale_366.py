import datetime
# import openpyxl as pyxl
import json
import uuid
import pandas as pd
from airflow.utils.log.logging_mixin import LoggingMixin
import hashlib

def create_text_hash(row, columns):
    # Объединяем значения столбцов в строку
    combined = ''.join(str(row[col]) for col in columns)
    # Создаем хеш SHA256 и преобразуем в hex-строку
    return hashlib.sha256(combined.encode()).hexdigest()

def transform_xl_to_json (path = '',sheet_name = 'Sheet1' , name_report = 'custom', name_pharm_chain = '36,6') -> dict:
    loger = LoggingMixin().log
    try:
        df = pd.read_excel(path , sheet_name)
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')
        df_drugstore = df[['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки']].drop_duplicates()
        df_product = df[['SKU Наименование', 'SKU ID', 'Производитель']].drop_duplicates()
   

        df_drugstore['hash_drugstore'] = df_drugstore.apply(create_text_hash, columns = ['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'Адрес аптеки'], axis=1)
        df_product['hash_product'] = df_product.apply(create_text_hash, columns = ['SKU Наименование', 'SKU ID', 'Производитель'], axis=1)

        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        df = df.merge(df_drugstore, on = ['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки'], how = 'left')
        df = df.merge(df_product, on = ['SKU Наименование', 'SKU ID', 'Производитель'], how = 'left')
        df_report = df[['uuid_report', 'Период', 'Количество, уп','Сумма ЗЦ, руб. без НДС', 'hash_drugstore', 'hash_product']]
        df_report.rename(columns = {'Период':'period', 'Количество, уп':'quantity',
        'Сумма ЗЦ, руб. без НДС':'total_cost'}, inplace=True)
        df_report['name_report'] = [name_report for x in range(len(df))]
        df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
        df_drugstore.rename(columns = {'Бренд аптеки': 'name', 'ЮЛ аптеки': 'legal_name', 'ИНН аптеки':'inn', 'ID аптеки':'id', 'Адрес аптеки':'address'}, inplace=True)
        df_product.rename(columns={'SKU Наименование':'name', 'SKU ID':'id', 'Производитель':'manufacturer'}, inplace=True)
        
        loger.info(f'Операция преобразования данных успешно выполнена!')

        return {
            'table_report':     df_report,
            'table_drugstor':   df_drugstore,
            'table_product':    df_product
            }
    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

    

if __name__ == "__main__":
    transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx')
    