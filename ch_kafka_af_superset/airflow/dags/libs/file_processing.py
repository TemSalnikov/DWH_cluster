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
        loger.error(f"Ошибка: каталог {directory} не найден")
        raise
    except PermissionError:
        loger.error(f"Ошибка: нет доступа к каталогу {directory}")
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

        res_list = cursor.fetchall()
        result = [x[0] for x in res_list]
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
        return [x for x in a if x not in b]

def check_new_folders(meta_folder_list, folders_list):
    loger = LoggingMixin().log
    # query = 'select name_folder  from files.folders c ' \
    # ' join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}'' '
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
    # 'join files.folders c on f.id_folder = c.id_folder and c.name_folder = '{folder}''' \
    # ' join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}'' '

    # files_list = get_list_files(directory, folder, pattern)
    # meta_files_list = get_meta_data(db_config, query)

    result = list_difference(files_list, meta_files_list)
    loger.info(f'Список необработанных файлов: {result}')
    
    return result

def _write_meta_directory(db_config, directory):
    loger = LoggingMixin().log
    conn = None
    query_check = f"""select name_dir from files.directories d 
                       where d.name_dir = '{directory}'"""
    query_insert = f"""insert into files.directories
                        (name_dir) values ('{directory}')"""
    query_get_id_dir = f"""select id_dir from files.directories d 
                       where d.name_dir = '{directory}'"""
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(query_check)
        check = cursor.fetchall()
        if check:
            loger.info(f'Директория {directory} была записана ранее')
        else:
            loger.info(f'Подготовлен запрос для выполнения: {query_insert}')
            cursor.execute(query_insert)
            conn.commit()
            # answer = cursor.fetchall()
            loger.info(f'Выполнена запись директории {directory}')
        cursor.execute(query_get_id_dir)
        id_dir = cursor.fetchone()
        loger.info(f'Выполнен query_get_id_dir с резуьтатом {id_dir[0]}')
        return id_dir[0]
    except Exception as e:
        loger.error(f"Ошибка при работе с PostgreSQL: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def _write_meta_folder(db_config, directory, folder):
    id_dir = _write_meta_directory(db_config, directory)
    loger = LoggingMixin().log
    conn = None
    query_check = f"""select name_folder from files.folders c 
                join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}'
                and c.name_folder = '{folder}'""" 
    query_insert = f"""insert into files.folders
                        (name_folder, id_dir) values ('{folder}', {id_dir})"""
    query_get_id_folder = f"""select id_folder from files.folders c 
                join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}'
                and c.name_folder = '{folder}'""" 
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        cursor.execute(query_check)
        check = cursor.fetchall()
        if check:
            loger.info(f'Папка {folder} была записана ранее')
        else:
            loger.info(f'Подготовлен запрос для выполнения: {query_insert}')
            cursor.execute(query_insert)
            conn.commit()
            # answer = cursor.fetchall()
            loger.info(f'Выполнена запись папки {folder}')
        cursor.execute(query_get_id_folder)
        result = cursor.fetchone()
        return result[0]
    except Exception as e:
        loger.error(f"Ошибка при работе с PostgreSQL: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def write_meta_file(db_config, directory, folder, file):
    id_folder = _write_meta_folder(db_config, directory, folder)
    loger = LoggingMixin().log
    conn = None
    query_check = f"""select name_file  from files.files f 
                        join files.folders c on f.id_folder = c.id_folder and c.name_folder = '{folder}'
                        join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}'
                        and f.name_file = '{file}'"""
    query_insert = f"""insert into files.files
                        (name_file, id_folder) values ('{file}', {id_folder})"""
    query_get_id_file = f"""select id_file  from files.files f 
                        join files.folders c on f.id_folder = c.id_folder and c.name_folder = '{folder}'
                        join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{directory}' 
                        and f.name_file = '{file}'""" 
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        loger.info(f'Подготовлен запрос для выполнения: {query_check}')
        cursor.execute(query_check)
        check = cursor.fetchall()
        if check:
            loger.info(f'Файл {file} был записан ранее')
        else:
            loger.info(f'Подготовлен запрос для выполнения: {query_insert}')
            cursor.execute(query_insert)
            conn.commit()
            # answer = cursor.fetchall()
            loger.info(f'Выполнена запись файла {file}')
        cursor.execute(query_get_id_file)
        result = cursor.fetchone()
        return result[0]
    except Exception as e:
        loger.error(f"Ошибка при работе с PostgreSQL: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()