"""ETL task functions called by the Airflow DAG (Task 3.3)."""

from pathlib import Path
import hashlib
import json
import logging
import os
import sys
import pandas as pd

# The container sets this path because Airflow imports the DAG from a mounted folder.
configured_root = os.environ.get("PRESIGHT_PROJECT_ROOT")
if configured_root:
    ROOT = Path(configured_root)
else:
    ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/results/deepak_shinghal/03_big_data/airflow"
sys.path.insert(0, str(ROOT / "solutions/submissions/deepak_shinghal/01_foundations"))
sys.path.insert(0, str(ROOT / "solutions/submissions/deepak_shinghal/02_sql_and_viz"))
from etl_pipeline import (
    load_projects,
    load_employees,
    transform_projects,
    clean_employees,
)
from etl_full import load_transactions, enrich_transactions

LOG = logging.getLogger(__name__)


def run_folder(context):
    # A short folder name derived from the run ID keeps separate runs' files apart.
    run_id = context["run_id"]
    folder_name = hashlib.sha256(run_id.encode()).hexdigest()[:16]
    folder = OUT / "runs" / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def task_extract_projects(**context):
    projects = load_projects(ROOT / "datasets/projects.csv")
    context["ti"].xcom_push(key="projects_raw_count", value=len(projects))
    return len(projects)


def task_extract_employees(**context):
    employees = load_employees(ROOT / "datasets/employees.csv")
    context["ti"].xcom_push(key="employees_raw_count", value=len(employees))
    return len(employees)


def task_extract_transactions(**context):
    transactions = load_transactions(ROOT / "datasets/transactions.json")
    context["ti"].xcom_push(key="transactions_raw_count", value=len(transactions))
    return len(transactions)


def run_data_quality_checks(df, dataset_name, key_columns):
    result = {
        "dataset": dataset_name,
        "row_count": len(df),
        "completeness_pct": {},
        "duplicate_primary_ids": 0,
    }
    for column in key_columns:
        if column not in df.columns:
            raise ValueError(dataset_name + ": missing column " + column)

        values = df[column].astype("string").str.strip().replace("", pd.NA)
        completeness = 0.0
        if len(df) > 0:
            completeness = float(values.notna().mean() * 100)
        result["completeness_pct"][column] = completeness
        if completeness < 80:
            raise ValueError(
                f"{dataset_name}.{column}: completeness {completeness}% is below 80%"
            )
    primary_column = key_columns[0]
    result["duplicate_primary_ids"] = int(
        df[primary_column].dropna().duplicated().sum()
    )
    if result["duplicate_primary_ids"]:
        raise ValueError(dataset_name + ": duplicate primary IDs")
    return result


def task_validate_data_quality(**context):
    projects = load_projects(ROOT / "datasets/projects.csv")
    employees = load_employees(ROOT / "datasets/employees.csv")
    transactions = load_transactions(ROOT / "datasets/transactions.json")
    results = {
        "projects": run_data_quality_checks(
            projects, "projects", ["project_id", "project_name"]
        ),
        "employees": run_data_quality_checks(
            employees, "employees", ["employee_id", "email"]
        ),
        "transactions": run_data_quality_checks(
            transactions, "transactions", ["transaction_id", "project_id"]
        ),
    }
    missing_projects = ~transactions["project_id"].isin(projects["project_id"])
    if missing_projects.any():
        raise ValueError(
            "Transactions reference unknown projects: "
            + str(int(missing_projects.sum()))
        )
    context["ti"].xcom_push(key="dq_results", value=results)
    LOG.info("DQ gate passed: %s", results)
    return results


def task_transform_and_enrich(**context):
    raw_projects = load_projects(ROOT / "datasets/projects.csv")
    raw_employees = load_employees(ROOT / "datasets/employees.csv")
    raw_transactions = load_transactions(ROOT / "datasets/transactions.json")
    projects = transform_projects(raw_projects)
    employees = clean_employees(raw_employees)
    transactions = enrich_transactions(raw_transactions, projects, employees)
    folder = run_folder(context)
    # Save intermediate tables to shared disk; retries overwrite only this run's files.
    projects.to_csv(folder / "projects_stage.csv", index=False)
    employees.to_csv(folder / "employees_stage.csv", index=False)
    transactions.to_csv(folder / "transactions_stage.csv", index=False)
    (folder / "quality_summary.json").write_text(
        json.dumps(employees.attrs["quality_summary"], indent=2) + "\n"
    )
    counts = {
        "projects_clean_count": len(projects),
        "employees_clean_count": len(employees),
        "transactions_clean_count": len(transactions),
    }
    for key, count in counts.items():
        context["ti"].xcom_push(key=key, value=count)
    return counts


def write_outputs(projects, employees, transactions, folder):
    paths = []
    for name, table in [
        ("projects", projects),
        ("employees", employees),
        ("transactions", transactions),
    ]:
        path = folder / (name + "_clean.csv")
        table.to_csv(path, index=False)
        paths.append(str(path))
        LOG.info("Wrote %s (%d rows)", path, len(table))
    return paths


def task_load_to_output(**context):
    folder = run_folder(context)
    projects = pd.read_csv(folder / "projects_stage.csv")
    employees = pd.read_csv(folder / "employees_stage.csv")
    transactions = pd.read_csv(folder / "transactions_stage.csv")
    paths = write_outputs(projects, employees, transactions, folder)
    context["ti"].xcom_push(key="files_written", value=paths)
    return paths


def task_generate_pipeline_report(**context):
    ti = context["ti"]
    lines = [
        "Presight Airflow pipeline report",
        "Run ID: " + context["run_id"],
        "Logical execution date: " + context["logical_date"].isoformat(),
    ]
    for name in ["projects", "employees", "transactions"]:
        raw = ti.xcom_pull(task_ids="extract_" + name, key=name + "_raw_count")
        clean = ti.xcom_pull(task_ids="transform_and_enrich", key=name + "_clean_count")
        if raw is None or clean is None:
            raise ValueError("Missing row-count XCom for " + name)
        lines.append(name + " raw/clean: " + str(raw) + "/" + str(clean))
    quality = ti.xcom_pull(task_ids="validate_data_quality", key="dq_results")
    paths = ti.xcom_pull(task_ids="load_to_output", key="files_written")
    if quality is None or paths is None:
        raise ValueError("Missing quality or output-path XCom")
    lines.append("DQ results: " + json.dumps(quality, indent=2))
    lines.append("Files written:")
    lines.extend(paths)
    # Date names the report; the run folder separates runs even when their dates match.
    report = run_folder(context) / (
        "pipeline_report_" + context["logical_date"].date().isoformat() + ".txt"
    )
    report.write_text("\n".join(lines) + "\n")
    ti.xcom_push(key="report_path", value=str(report))
    LOG.info("Report written: %s", report)
    return str(report)


def log_task_failure(context):
    LOG.error(
        "Task failed: %s; run=%s; error=%s",
        context["task_instance"].task_id,
        context.get("run_id"),
        context.get("exception"),
    )
