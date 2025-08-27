from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.models import Param, Variable
from airflow.utils.task_group import TaskGroup
from airflow.providers.postgres.hooks.postgres import PostgresHook



default_args = {
    'owner': 'airflow',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

REPORT_TYPES = [
    "GENERAL_PRICING_REPORT",
    "GENERAL_REPORT_ON_MOVEMENT",
    "GENERAL_REPORT_ON_REMAINING_ITEMS",
    "GENERAL_REPORT_ON_DISPOSAL"
]

def parse_json_output(output):
    import json
    try:
        return json.loads(output.split('\n')[-1])
    except:
        return {}

def _skip_if_fail(task_bash, **context):
    # ti = context["ti"]
    # Получаем результат из XCom
    result = str(context["ti"].xcom_pull(task_ids=task_bash)).strip().lower()
    print(f'result:{result}')
    return result != "false" 

        
    

def init_api_state():
    """Инициализация состояния API перед запуском DAG"""
    # import psycopg2
    try:
        # conn = psycopg2.connect(
        #     dbname=os.getenv('POSTGRES_DB', 'airflow'),
        #     user=os.getenv('POSTGRES_USER', 'airflow'),
        #     password=os.getenv('POSTGRES_PASSWORD', 'airflow'),
        #     host=os.getenv('POSTGRES_HOST', 'postgres'),
        #     port=os.getenv('POSTGRES_PORT', '5432')
        # )
        # cur = conn.cursor()

        hook = PostgresHook(postgres_conn_id="mdlp_postgres_conn")
        conn = hook.get_conn()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mdlp_api_state (
                id SERIAL PRIMARY KEY,
                key VARCHAR(50) UNIQUE NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            
            INSERT INTO mdlp_api_state (key, value)
            VALUES ('last_request_time', '0')
            ON CONFLICT (key) DO NOTHING;
        """)
        conn.commit()
        return "API state initialized"
    except Exception as e:
        return f"Error initializing API state: {str(e)}"

def save_metadata_to_postgres(**context):
    """Сохранение метаданных отчетов в PostgreSQL"""
    hook = PostgresHook(postgres_conn_id="mdlp_postgres_conn")
    conn = hook.get_conn()
    cursor = conn.cursor()
    
    # Создаем таблицу если не существует
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mdlp_report_meta (
        id SERIAL PRIMARY KEY,
        report_type VARCHAR(100) NOT NULL,
        date_to DATE NOT NULL,
        processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Собираем результаты из всех задач
    meta_data = []
    for report_type in REPORT_TYPES:
        task_id = f"process.{report_type}.process_{report_type}"
        result = context['ti'].xcom_pull(task_ids=task_id)
        if result and result.get('status') in ('success', 'empty'):
            meta_data.append((result['report_type'], result['date_to']))
    
    # Вставляем данные
    if meta_data:
        cursor.executemany(
            "INSERT INTO mdlp_report_meta (report_type, date_to) VALUES (%s, %s)",
            meta_data
        )
    
    conn.commit()
    cursor.close()
    conn.close()
    return f"Inserted {len(meta_data)} records"

with DAG(
    dag_id='wf_mdlp_kafka_mart_mdlp_report_bash',
    schedule_interval='0 9 * * 2',
    start_date=datetime(2023, 1, 1),
    default_args=default_args,
    catchup=False,
    params={
        'period_type': Param(
            "IC_Period_Week",
            description='Тип периода (IC_Period_Month или IC_Period_Week)'
        ),
        'dates_to': Param(
            [datetime.today().strftime("%Y-%m-%d")],
            type='array',
            description='Даты окончания периода'
        )
    }
) as dag:

    # ===== Инициализация состояния =====
    init_state = PythonOperator(
        task_id='init_api_state',
        python_callable=init_api_state
    )
    # ===== Аутентификация =====
    get_auth_code = BashOperator(
        task_id='get_auth_code',
        bash_command='python /opt/airflow/dags/libs/mdlp_api_utils.py get_auth_code',
        do_xcom_push=True
    )

    sign_auth_code = BashOperator(
        task_id='sign_auth_code',
        bash_command=(
            'python /opt/airflow/dags/libs/sign_data.py '
            '{{ ti.xcom_pull(task_ids="get_auth_code") | tojson }}'
        ),
        do_xcom_push=True
    )

    get_session_token = BashOperator(
        task_id='get_session_token',
        bash_command=(
            'python /opt/airflow/dags/libs/mdlp_api_utils.py get_session_token '
            '--auth-code {{ ti.xcom_pull(task_ids="get_auth_code") | tojson }} '
            '--signature {{ ti.xcom_pull(task_ids="sign_auth_code") | tojson }}'
        ),
        do_xcom_push=True
    )
 
    prev_group_end = None
    # ===== Обработка отчетов =====
    with TaskGroup(group_id='process') as process_group:
        for report_type in REPORT_TYPES:
            with TaskGroup(group_id=report_type) as report_group:
                # Создание задачи на отчет
                create_task = BashOperator(
                    task_id=f'create_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_api_utils.py create_report_task '
                        '--token {{ ti.xcom_pull(task_ids="get_session_token") | tojson }} '
                        f'--report-type {report_type} '
                        '--period-type {{ params.period_type }} '
                        '--date-to {{ params.dates_to[0] }}'
                    ),
                    do_xcom_push=True
                )

                # Проверка статуса (с повторными попытками)
                check_status = BashOperator(
                    task_id=f'check_status_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_api_utils.py check_report_status '
                        '--token {{ ti.xcom_pull(task_ids="get_session_token") | tojson }} '
                        f'--task-id {{{{ ti.xcom_pull(task_ids="process.{report_type}.create_{report_type}") | tojson }}}}'
                    ),
                    retries=24 * 12,  # 24 часа (проверка каждые 5 минут)
                    retry_delay=timedelta(minutes=5),
                    do_xcom_push=True
                )
                
                # Скачивание отчета
                download_report = BashOperator(
                    task_id=f'download_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_api_utils.py download_report '
                        '--token {{ ti.xcom_pull(task_ids="get_session_token") | tojson }} '
                        f'--result-id {{{{ ti.xcom_pull(task_ids="process.{report_type}.check_status_{report_type}") | tojson }}}} '
                        f'--report-type {report_type} '
                        '--date-to "{{ params.dates_to[0] }}"'
                    ),
                    do_xcom_push=True
                ) 
                extract_report = BashOperator(
                    task_id=f'extract_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_report_processor.py extract_report '
                        f'--zip-path {{{{ ti.xcom_pull(task_ids="process.{report_type}.download_{report_type}") }}}} '
                    ),
                    do_xcom_push=True
                )

                check_data_report = BashOperator(
                    task_id=f'check_data_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_report_processor.py check_data_inreport '
                        f'--csv-path {{{{ ti.xcom_pull(task_ids="process.{report_type}.extract_{report_type}") }}}} '
                    ),
                    do_xcom_push=True
                )

                skip_check = ShortCircuitOperator(
                    task_id=f"skip_check_{report_type}",
                    python_callable=_skip_if_fail,
                    op_kwargs={"task_bash": f"process.{report_type}.check_data_{report_type}"},
                    provide_context=True,
                    dag=dag,
                    )

                process_report = BashOperator(
                    task_id=f'process_{report_type}',
                    bash_command=(
                        'python /opt/airflow/dags/libs/mdlp_report_processor.py process_report '
                        f'--csv-path {{{{ ti.xcom_pull(task_ids="process.{report_type}.extract_{report_type}") }}}} '
                        f'--report-type {report_type} '
                        '--date-to "{{ params.dates_to[0] }}"'
                    ),
                    do_xcom_push=True
                )


                # if prev_group_end is not None:
                #     prev_group_end >> create_task

                # Оркестрация внутри группы отчета
                create_task >> check_status >> download_report >> extract_report >> check_data_report >> skip_check >> process_report
                # prev_group_end = download_report
            
            

            # report_group >> process_report

                
    # with TaskGroup(group_id='process') as process_group:
    #     for report_type in REPORT_TYPES:
    #         # Обработка и отправка в Kafka
    #         process_report = BashOperator(
    #             task_id=f'process_{report_type}',
    #             bash_command=(
    #                 'python /opt/airflow/dags/libs/mdlp_report_processor.py '
    #                 f'--zip-path {{{{ ti.xcom_pull(task_ids="download.{report_type}.download_{report_type}") }}}} '
    #                 f'--report-type {report_type} '
    #                 '--date-to "{{ params.dates_to[0] }}"'
    #             ),
    #             do_xcom_push=True
    #         )




    # # ===== Сохранение метаданных =====
    # save_metadata = PythonOperator(
    #     task_id='save_metadata',
    #     python_callable=save_metadata_to_postgres,
    #     provide_context=True
    # )

    # ===== Очистка =====
    cleanup = BashOperator(
        task_id='cleanup',
        bash_command='echo "Removing temporary files" && rm -f /tmp/mdlp/*.zip /tmp/mdlp/extracted/*.csv',
        trigger_rule='all_done'
    )

    # ===== Оркестрация =====
    init_state >> get_auth_code >> sign_auth_code >> get_session_token >> process_group
    process_group >> cleanup