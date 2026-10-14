"""Run the ETL and quality reports using DATA_DIR and OUTPUT_DIR."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import logging
import os
import sys
import time
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "datasets"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs"))
DQ_OUTPUT_DIR = OUTPUT_DIR / "results/deepak_shinghal/04_infrastructure"
SUBMISSION = ROOT / "solutions/submissions/deepak_shinghal"
# Reuse the completed Task 2.2 logic rather than copying its cleaning rules.
for folder in ["01_foundations", "02_sql_and_viz", "04_infrastructure"]:
    sys.path.insert(0, str(SUBMISSION / folder))
from etl_pipeline import (
    load_projects,
    load_employees,
    transform_projects,
    clean_employees,
)
from etl_full import load_transactions, enrich_transactions
from data_quality import load_rules, run_data_quality_checks, write_dq_report

LOG = logging.getLogger(__name__)


def write_outputs(projects, employees, transactions):
    for name, table in [
        ("projects", projects),
        ("employees", employees),
        ("transactions", transactions),
    ]:
        table.to_csv(OUTPUT_DIR / (name + "_clean.csv"), index=False)


def run_pipeline():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    start = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: check raw values before parsing/cleaning can hide invalid inputs.
    raw = {
        "projects": pd.read_csv(DATA_DIR / "projects.csv"),
        "employees": pd.read_csv(DATA_DIR / "employees.csv"),
        "transactions": pd.read_json(DATA_DIR / "transactions.json"),
        "employees_salary_history": pd.read_csv(
            DATA_DIR / "employees_salary_history.csv"
        ),
    }
    rules = load_rules()
    reports = {}
    for name, table in raw.items():
        reports[name] = run_data_quality_checks(table, name, tables=raw, config=rules)
        write_dq_report(reports[name], DQ_OUTPUT_DIR)

    loaded_projects = load_projects(DATA_DIR / "projects.csv")
    loaded_employees = load_employees(DATA_DIR / "employees.csv")
    loaded_transactions = load_transactions(DATA_DIR / "transactions.json")
    projects = transform_projects(loaded_projects)
    employees = clean_employees(loaded_employees)
    transactions = enrich_transactions(loaded_transactions, projects, employees)

    write_outputs(projects, employees, transactions)
    quality = employees.attrs["quality_summary"]
    (OUTPUT_DIR / "quality_summary.json").write_text(
        json.dumps(quality, indent=2) + "\n"
    )
    (DQ_OUTPUT_DIR / "dq_results.json").write_text(json.dumps(reports, indent=2) + "\n")
    elapsed = time.perf_counter() - start
    counts = {}
    for name, table in [
        ("projects", projects),
        ("employees", employees),
        ("transactions", transactions),
    ]:
        counts[name] = {"before": len(raw[name]), "after": len(table)}
    failed_checks = {}
    for name, report in reports.items():
        failed_checks[name] = report["checks_failed"]
    summary = {
        "run_at": datetime.now(ZoneInfo("Asia/Dubai")).isoformat(),
        "row_counts": counts,
        "execution_seconds": elapsed,
        "under_30_seconds": elapsed < 30,
        "quality_issues_and_fixes": quality,
        "dq_checks_failed": failed_checks,
        "dq_scope": "Raw source data; failures remain visible for owner review.",
    }
    (OUTPUT_DIR / "pipeline_summary.txt").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    LOG.info(
        "Processed %d transactions in %.3f seconds; outputs: %s",
        len(transactions),
        elapsed,
        OUTPUT_DIR,
    )
    return summary


if __name__ == "__main__":
    run_pipeline()
