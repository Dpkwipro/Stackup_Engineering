"""Schedule the daily ETL at 06:00 Dubai time (Task 3.3)."""

from datetime import timedelta
from pathlib import Path
import os
import sys
import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

# The DAG is mounted into /opt/airflow/dags; helper modules live in the repo mount.
configured_root = os.environ.get("PRESIGHT_PROJECT_ROOT")
if configured_root:
    ROOT = Path(configured_root)
else:
    ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "solutions/submissions/deepak_shinghal/03_big_data"))
from airflow_tasks import (
    task_extract_projects,
    task_extract_employees,
    task_extract_transactions,
    task_validate_data_quality,
    task_transform_and_enrich,
    task_load_to_output,
    task_generate_pipeline_report,
    log_task_failure,
)

# Timezone-aware start_date makes 0 6 * * * mean 06:00 DUBAI, not 06:00 UTC.
default_args = {
    "owner": "deepak_shinghal",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
    "email_on_failure": False,
    "on_failure_callback": log_task_failure,
}

with DAG(
    dag_id="presight_etl_pipeline",
    default_args=default_args,
    start_date=pendulum.datetime(2025, 1, 1, tz="Asia/Dubai"),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["presight", "etl", "assessment"],
) as dag:
    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    extract_projects = PythonOperator(
        task_id="extract_projects", python_callable=task_extract_projects
    )
    extract_employees = PythonOperator(
        task_id="extract_employees", python_callable=task_extract_employees
    )
    extract_transactions = PythonOperator(
        task_id="extract_transactions", python_callable=task_extract_transactions
    )
    validate_dq = PythonOperator(
        task_id="validate_data_quality", python_callable=task_validate_data_quality
    )
    transform = PythonOperator(
        task_id="transform_and_enrich", python_callable=task_transform_and_enrich
    )
    load = PythonOperator(task_id="load_to_output", python_callable=task_load_to_output)
    report = PythonOperator(
        task_id="generate_pipeline_report",
        python_callable=task_generate_pipeline_report,
    )
    # A list branches to three independent tasks; the gate waits for ALL of them.
    start >> [extract_projects, extract_employees, extract_transactions] >> validate_dq
    validate_dq >> transform >> load >> report >> end
