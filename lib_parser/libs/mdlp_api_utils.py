import argparse
import json
import sys
from datetime import datetime
from mdlp_api_client import (  # Предполагается, что этот модуль уже создан
    get_auth_code,
    get_session_token,
    create_report_task,
    check_report_status,
    download_report
)

def main():
    parser = argparse.ArgumentParser(description='MDLP API Utilities')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Команда для получения кода аутентификации
    auth_parser = subparsers.add_parser('get_auth_code')
    
    # Команда для получения токена сессии
    token_parser = subparsers.add_parser('get_session_token')
    token_parser.add_argument('--auth-code', required=True)
    token_parser.add_argument('--signature', required=True)
    
    # Команда для создания задачи отчета
    task_parser = subparsers.add_parser('create_report_task')
    task_parser.add_argument('--token', required=True)
    task_parser.add_argument('--report-type', required=True)
    task_parser.add_argument('--period-type', required=True)
    task_parser.add_argument('--date-to', required=True)
    
    # Команда для проверки статуса
    status_parser = subparsers.add_parser('check_report_status')
    status_parser.add_argument('--token', required=True)
    status_parser.add_argument('--task-id', required=True)
    
    # Команда для скачивания отчета
    download_parser = subparsers.add_parser('download_report')
    download_parser.add_argument('--token', required=True)
    download_parser.add_argument('--result-id', required=True)
    download_parser.add_argument('--report-type', required=True)
    download_parser.add_argument('--date-to', required=True)
    
    args = parser.parse_args()
    
    try:
        if args.command == 'get_auth_code':
            result = get_auth_code()
            print(result)
            
        elif args.command == 'get_session_token':
            result = get_session_token(args.auth_code, args.signature)
            print(result)
            
        elif args.command == 'create_report_task':
            result = create_report_task(
                args.token, 
                args.report_type,
                args.period_type,
                args.date_to
            )
            print(result)
            
        elif args.command == 'check_report_status':
            result = check_report_status(args.token, args.task_id)
            print(result)
            
        elif args.command == 'download_report':
            result = download_report(
                args.token,
                args.result_id,
                args.report_type,
                args.date_to
            )
            print(result)
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()