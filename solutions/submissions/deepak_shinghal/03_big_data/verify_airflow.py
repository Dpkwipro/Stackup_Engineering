"""Verify DAG settings and failure propagation inside the Airflow container."""

from pathlib import Path
import json
import pendulum
import pandas as pd
from airflow.models import DagBag
from airflow_tasks import run_data_quality_checks

OUT = Path("/opt/airflow/project/outputs/results/deepak_shinghal/03_big_data/airflow")


def reject_bad_fixture(**context):
    # Three missing IDs out of ten = 70% completeness; this must fail below 80%.
    fixture = pd.DataFrame(
        {"project_id": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", None, None, None]}
    )
    return run_data_quality_checks(fixture, "projects", ["project_id"])


def main():
    bag = DagBag("/opt/airflow/dags", include_examples=False)
    if bag.import_errors:
        raise ValueError(str(bag.import_errors))
    dag = bag.get_dag("presight_etl_pipeline")
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.timezone.name == "Asia/Dubai"
    assert dag.schedule_interval == "0 6 * * *"
    extracts = {"extract_projects", "extract_employees", "extract_transactions"}
    gate = dag.get_task("validate_data_quality")
    assert gate.upstream_task_ids == extracts
    for task_id in extracts:
        assert dag.get_task(task_id).upstream_task_ids == {"start"}
    assert gate.retries == 2
    assert gate.retry_delay.total_seconds() == 300

    local = pendulum.datetime(2026, 10, 13, 6, 0, tz="Asia/Dubai")
    evidence = {
        "dag_id": dag.dag_id,
        "schedule": dag.schedule_interval,
        "timezone": dag.timezone.name,
        "example_local_schedule": local.isoformat(),
        "example_utc_schedule": local.in_timezone("UTC").isoformat(),
        "retries": gate.retries,
        "retry_delay_seconds": gate.retry_delay.total_seconds(),
        "parallel_extract_dependencies": True,
        "catchup": dag.catchup,
        "max_active_runs": dag.max_active_runs,
    }
    for task in dag.tasks:
        task.retries = 0  # Verification only; no source file changes.
    gate.python_callable = reject_bad_fixture
    # A new timestamp lets this verification run repeatedly without reusing old runs.
    run = dag.test(execution_date=pendulum.now("UTC"))
    states = {}
    for task in run.get_task_instances():
        states[task.task_id] = task.state
    assert states["validate_data_quality"] == "failed", states
    for task_id in [
        "transform_and_enrich",
        "load_to_output",
        "generate_pipeline_report",
        "end",
    ]:
        assert states[task_id] == "upstream_failed", states
    evidence["injected_failure_completeness_pct"] = 70
    evidence["failure_run_state"] = str(run.state)
    evidence["failure_task_states"] = states
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "failure_gate_verification.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
