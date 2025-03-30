#!/bin/bash

echo "Start install clickhouse-connect"
pip install clickhouse-connect
echo "Start superset"
superset run -h 0.0.0.0 -p 8088