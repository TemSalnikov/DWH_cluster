from datetime import datetime, timedelta
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

def extract_xls (path = '', name_report = 'Остатки+Закуп+Продажи', name_pharm_chain = 'Аптека 25') -> dict:
    loger = LoggingMixin().log
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = pd.read_excel(path , sheet_names[0])
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')

        param_row = df[df.iloc[:,0] == 'Параметры:'].index[0]
        # report_date = df.iloc[0,1]
        period = df.iloc[param_row,1].split(':')[1].strip()
        start_date, end_date = period.split(' - ')
        start_date = (start_date, "%Y-%m-%d")
        end_date = (end_date, "%Y-%m-%d")
        if start_date == end_date:
            end_date= end_date + timedelta(days = 1)

        df = dropna(how = 'all').reset_index(drop = True)
        start_row = df[df.iloc[:,0] == 'Склад'].index[0]
        headers = df.iloc[start_row].values
        df = df.iloc[start_row + 3] .copy()
        df.columns = headers


        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        # df['hash_drugstore'] = df.apply(create_text_hash, columns = ['Организация', 'ИНН', 'Склад'], axis=1)
        df.rename(columns = {'Склад':'product', 'Нач. остаток, шт.':'start_quantity', 'Приход, шт.':'received_quantity', 'Расход, шт.':'sale_quantity', 'Кон. остаток, шт.':'end_quantity'}, inplace=True)
        # df_drugstore = df[['hash_drugstore','drugstore', 'inn', 'address']].drop_duplicates()
        df_report = df[['uuid_report', 'product', 'start_quantity', 'received_quantity', 'sale_quantity', 'end_quantity']]
        df_report['name_report'] = [name_report for x in range(len(df))]
        df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        # df_report['report_date'] = [report_date for x in range(len(df))]
        df_report['start_date'] = [start_date for x in range(len(df))]
        df_report['end_date'] = [end_date for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
        return {
            'table_report':     df_report
            }

    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise



# def extract_xls (path, name_report, name_pharm_chain) -> dict:
#     match name_report:
#         case 'Закупки':
#             return extract_custom(path, name_report, name_pharm_chain)
#         case 'Остатки':
#             return extract_remain(path, name_report, name_pharm_chain)
#         case 'Продажи':
#             return extract_sale(path, name_report, name_pharm_chain)
#         case _:
#             return {}



if __name__ == "__main__":
    transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx')
