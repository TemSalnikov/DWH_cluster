#!/bin/bash

echo "Start install clickhouse-connect"
pip install clickhouse-connect
echo "Start install psycopg2-binary"
pip install psycopg2-binary
echo "Init superset"
./superset_init.sh
echo "Start superset"
superset run -h 0.0.0.0 -p 8088