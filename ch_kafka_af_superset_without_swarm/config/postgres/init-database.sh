#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER superset WITH PASSWORD 'superset';
    CREATE DATABASE superset;
    GRANT ALL PRIVILEGES ON DATABASE superset TO superset;
    ALTER USER superset WITH SUPERUSER;
    CREATE USER airflow WITH PASSWORD 'airflow';
    CREATE DATABASE airflow;
    GRANT ALL PRIVILEGES ON DATABASE airflow TO airflow;
    ALTER USER airflow WITH SUPERUSER;
EOSQL