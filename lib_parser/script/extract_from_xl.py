import datetime
# import openpyxl as pyxl
import json
import uuid
import pandas as pd
from airflow.utils.log.logging_mixin import LoggingMixin

def transform_xl_to_json (path = '',sheet_name = 'Sheet1' , name_report = '', name_pharm_chain = ''):
    loger = LoggingMixin().log
    try:
        df = pd.read_excel(path , sheet_name)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')
        df_drugstore = df[['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки']].drop_duplicates()
        df_supplier = df[['Поставщик', 'ИНН поставщика']].drop_duplicates()
        df_product = df[['SKU Наименование', 'SKU ID', 'Производитель']].drop_duplicates()
        df_drugstore['uuid_drugstore'] = [str(uuid.uuid4()) for x in range(len(df_drugstore))]
        df_supplier['uuid_supplier'] = [str(uuid.uuid4()) for x in range(len(df_supplier))]
        df_product['uuid_product'] = [str(uuid.uuid4()) for x in range(len(df_product))]
        df['uuid'] = [str(uuid.uuid4()) for x in range(len(df))]
        df = df.merge(df_drugstore, on = ['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки'], how = 'left')
        df = df.merge(df_supplier, on = ['Поставщик', 'ИНН поставщика'], how = 'left')
        df = df.merge(df_product, on = ['SKU Наименование', 'SKU ID', 'Производитель'], how = 'left')
        df_report = df[['uuid', 'Период', 'Количество, уп','Сумма ЗЦ, руб. без НДС', 'uuid_drugstore', 'uuid_supplier', 'uuid_product']]
        df_report.rename(columns = {'Период':'period', 'Количество, уп':'quantity',
        'Сумма ЗЦ, руб. без НДС':'total_cost'}, inplace=True)
        df_drugstore.rename(columns = {'Бренд аптеки': 'name', 'ЮЛ аптеки': 'legal_name', 'ИНН аптеки':'inn', 'ID аптеки':'id', 'Адрес аптеки':'address'}, inplace=True)
        df_supplier.rename(columns={'Поставщик':'name', 'ИНН поставщика':'inn'}, inplace=True)
        df_product.rename(columns={'SKU Наименование':'name', 'SKU ID':'id', 'Производитель':'manufacturer'}, inplace=True)
        dict_report = df_report.to_dict(orient="split")
        dict_drugstor = df_drugstore.to_dict(orient="split")
        dict_supplier = df_supplier.to_dict(orient="split")
        dict_product = df_product.to_dict(orient="split")
        dict_result = {
            'name_pharm_chain': name_pharm_chain,
            'name_report':      name_report,
            'processed_dttm':   str(datetime.datetime.now()),
            'table_report':     dict_report,
            'table_drugstor':   dict_drugstor,
            'table_suplier':    dict_supplier,
            'table_product':    dict_product
            }
        json_result = json.dumps(dict_result).encode('utf-8')
        loger.info(f'Операция преобразования данных успешно выполнена!')
        return json_result
    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise
    # print(df.head())
    # print (df.columns)
    

if __name__ == "__main__":
    transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx')
    