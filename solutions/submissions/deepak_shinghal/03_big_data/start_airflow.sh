#!/bin/bash
set -e

# Use this folder's Compose file even when launched from another directory.
cd "$(dirname "$0")"

# A running webserver needs its PID file; clean it only while Airflow is stopped.
running_container=$(docker compose -p presight-task3 ps --status running -q airflow)
if [ -z "$running_container" ]; then
    docker compose -p presight-task3 run --rm --no-deps --entrypoint sh airflow \
        -c 'rm -f /opt/airflow/airflow-webserver.pid'
fi

docker compose -p presight-task3 up -d airflow

for seconds in {30..1}; do
    echo "Waiting for Airflow: $seconds seconds remaining"
    sleep 1
done

if curl --fail --silent --output /dev/null --max-time 3 http://127.0.0.1:8082/login/; then
    echo "Airflow is ready. Open http://localhost:8082"
    echo "Username: admin"
    printf "Password: "
    docker compose -p presight-task3 exec -T airflow cat /opt/airflow/standalone_admin_password.txt
    echo
else
    echo "Airflow is not ready after 30 seconds. Check its logs:"
    echo "docker compose -p presight-task3 logs --tail 30 airflow"
    exit 1
fi
