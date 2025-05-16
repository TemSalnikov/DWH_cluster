# import glob
import os
import psycopg2 
from airflow.utils.log.logging_mixin import LoggingMixin

def get_list_files(directory, folder, pattern="*"):
    loger = LoggingMixin().log
    # """Возвращает список файлов, соответствующих шаблону."""
    try:
        with os.scandir(directory+folder) as entries:
            files = [entry.name for entry in entries if entry.is_file()
                     if entry.is_file() and not entry.name.startswith('.')]
        loger.info(f'Список файлов в каталоге: {files}')
        return files
    except Exception as e:
        loger.error(f"Произошла ошибка: {e}")
        raise


def get_list_folders(directory):
    # Возвращает список папок с использованием os.scandir 
    loger = LoggingMixin().log
    try:
        with os.scandir(directory) as entries:
            folders = [entry.name for entry in entries if entry.is_dir()]
        loger.info(f'Список папок в каталоге: {folders}')
        return folders
    except FileNotFoundError:
        loger.error(f"Ошибка: каталог '{directory}' не найден")
        raise
    except PermissionError:
        loger.error(f"Ошибка: нет доступа к каталогу '{directory}'")
        raise
    except Exception as e:
        loger.error(f"Произошла ошибка: {e}")
        raise

def get_meta_data(db_config, query, params=None):
    loger = LoggingMixin().log
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        result = cursor.fetchall()
        loger.info(f'Список обработанных файлов: {result}')  
        return result
    except Exception as e:
        loger.error(f"Ошибка при работе с PostgreSQL: {e}")
        raise
    finally:
        if conn:
            conn.close()

def list_difference(a, b):
    # Возвращает элементы из списка a, которых нет в списке b
    b_set = set(b)
    return [x for x in a if x not in b_set]

def check_new_folders(meta_folder_list, folders_list):
    loger = LoggingMixin().log
    # query = 'select name_folder  from files.folders c ' \
    # ' join files.directories d on c.id_dir = d.id_dir and d.name_dir = ''{directory}'' '
    # meta_folder_list = get_meta_data(db_config, query)
    # folders_list = get_list_folders(directory)
    result = list_difference(folders_list, meta_folder_list)
    if result: 
        loger.info(f'Список необработанных папок: {result}')
        return result
    else:
        result = max(folders_list)
        loger.info(f'Список необработанных папок: {result}')
        return [result]


def check_new_files(files_list, meta_files_list):
    loger = LoggingMixin().log
    # query = 'select name_file  from files.files f ' \
    # 'join files.folders c on f.id_folder = c.id_folder and c.name_folder = ''{folder}''' \
    # ' join files.directories d on c.id_dir = d.id_dir and d.name_dir = ''{directory}'' '

    # files_list = get_list_files(directory, folder, pattern)
    # meta_files_list = get_meta_data(db_config, query)

    result = list_difference(files_list, meta_files_list)
    loger.info(f'Список необработанных файлов: {result}')
    
    return result