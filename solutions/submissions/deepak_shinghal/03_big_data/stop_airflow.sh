#!/bin/bash
set -e

cd "$(dirname "$0")"
docker compose -p presight-task3 stop airflow

# Remove the saved PID only after its webserver has stopped.
docker compose -p presight-task3 run --rm --no-deps --entrypoint sh airflow \
    -c 'rm -f /opt/airflow/airflow-webserver.pid'

echo "Airflow stopped and its old webserver PID file cleared."
