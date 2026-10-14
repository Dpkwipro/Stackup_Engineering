"""Run transaction ETL, business SQL, benchmarks and the dashboard (Pillar 2)."""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import json
import logging
import sqlite3
import statistics
import sys
import time
import shutil
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]

HERE = Path(__file__).resolve().parent
DATA = ROOT / "datasets"
FOUNDATIONS = HERE.parent / "01_foundations"
FOUNDATION_OUTPUT = ROOT / "outputs/results/deepak_shinghal/01_foundations"
OUT = ROOT / "outputs/results/deepak_shinghal/02_sql_and_viz"

LOG = logging.getLogger(__name__)


def load_transactions(filepath):
    with open(filepath, encoding="utf-8") as source_file:

        records = json.load(source_file)

    transactions = pd.json_normalize(records)

    transactions["transaction_date"] = pd.to_datetime(
        transactions["transaction_date"], format="%Y-%m-%d", errors="raise"
    )

    if transactions["transaction_date"].isna().any():
        raise ValueError("Missing transaction date")

    missing_ids = transactions["transaction_id"].isna()

    repeated_ids = transactions["transaction_id"].duplicated()
    if missing_ids.any() or repeated_ids.any():
        raise ValueError("Transaction IDs must be present and unique")

    transactions["amount"] = pd.to_numeric(transactions["amount"], errors="raise")

    correct_currency = transactions["currency"] == "AED"
    if not correct_currency.all():
        raise ValueError("Non-AED currency: add currency conversion before amount_aed")

    transactions["approved_by"] = (
        transactions["approved_by"].astype("string").str.strip()
    )

    transactions["approved_by"] = transactions["approved_by"].replace("", pd.NA)
    return transactions


def enrich_transactions(transactions, projects, employees):
    project_lookup = projects[["project_id", "project_name", "department"]]

    enriched = transactions.merge(
        project_lookup,
        on="project_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched_projects = enriched["_merge"] != "both"
    if unmatched_projects.any():
        raise ValueError("A transaction references an unknown project")

    enriched = enriched.drop(columns=["_merge"])

    employee_lookup = employees[["employee_id", "full_name"]].copy()

    employee_lookup = employee_lookup.rename(columns={"employee_id": "approved_by"})
    enriched = enriched.merge(
        employee_lookup, on="approved_by", how="left", validate="many_to_one"
    )

    enriched["full_name"] = enriched["full_name"].fillna("Unknown approver")

    # Task 2.2 defines is_approved as an approver ID being present.
    enriched["is_approved"] = enriched["approved_by"].notna()
    # Preserve original amount as null for audit. Only reporting amount_aed fills 0.
    reporting_amounts = enriched["amount"].fillna(0)
    enriched["amount_aed"] = reporting_amounts.astype(float)

    enriched["transaction_year_month"] = enriched["transaction_date"].dt.strftime(
        "%Y-%m"
    )

    if len(enriched) != len(transactions):
        raise ValueError("Enrichment changed the transaction count")
    return enriched


def read_sql_sections(filename, labels):
    source = (HERE / filename).read_text()

    sections = {}
    current_label = None

    for line in source.splitlines():
        text = line.strip()
        if (
            text
            == "-- MEASURED BENCHMARK (generated; see benchmark_results.json for all runs)"
        ):
            break
        if text.startswith("-- "):
            possible_label = text[3:]
            if possible_label in labels:
                current_label = possible_label
                sections[current_label] = []
                continue
        if current_label is not None:
            sections[current_label].append(line)

    for label in labels:
        if label not in sections:
            raise ValueError("Missing SQL section: " + label + " in " + filename)
        sections[label] = "\n".join(sections[label]).strip()
    return sections


def read_count(connection, sql_query):
    cursor = connection.execute(sql_query)
    result_row = cursor.fetchone()
    return result_row[0]


def prepare_warehouse(projects, employees, transactions):
    database = OUT / "analytics.sqlite"

    shutil.copyfile(FOUNDATION_OUTPUT / "foundations.sqlite", database)

    connection = sqlite3.connect(database)
    try:

        connection.execute("PRAGMA foreign_keys=ON")

        projects.to_sql("projects", connection, index=False)
        employees.to_sql("employees", connection, index=False)

        staging_transactions = transactions.copy()
        staging_transactions["transaction_date"] = staging_transactions[
            "transaction_date"
        ].dt.strftime("%Y-%m-%d")
        staging_transactions.to_sql("transactions", connection, index=False)

        source_count = read_count(connection, "SELECT COUNT(*) FROM transactions")
        fact_count = read_count(connection, "SELECT COUNT(*) FROM fact_transactions")

        mismatches = read_count(
            connection,
            """SELECT COUNT(*) FROM transactions t
          LEFT JOIN fact_transactions f USING(transaction_id)
          LEFT JOIN dim_project p ON p.project_key=f.project_key
          LEFT JOIN dim_vendor v ON v.vendor_key=f.vendor_key
          LEFT JOIN dim_date d ON d.date_key=f.date_key
          WHERE f.transaction_key IS NULL OR p.project_id IS NOT t.project_id
            OR v.vendor_id IS NOT t.vendor_id OR d.full_date IS NOT t.transaction_date
            OR f.amount IS NOT t.amount OR f.currency IS NOT t.currency
            OR f.category IS NOT t.category OR f.payment_status IS NOT t.payment_status""",
        )

        current_mismatches = read_count(
            connection,
            """SELECT COUNT(*) FROM employees e
          LEFT JOIN dim_employee d ON d.employee_id=e.employee_id AND d.is_current=1
          WHERE d.employee_key IS NULL OR d.full_name IS NOT e.full_name
            OR d.email IS NOT e.email OR d.salary IS NOT e.salary""",
        )

        project_mismatches = read_count(
            connection,
            """SELECT COUNT(*) FROM projects p
          LEFT JOIN dim_project d USING(project_id)
          WHERE d.project_key IS NULL OR d.budget IS NOT p.budget
             OR d.actual_cost IS NOT p.actual_cost OR d.status IS NOT p.status""",
        )

        wrong_count = source_count != fact_count
        wrong_transactions = mismatches > 0
        wrong_employees = current_mismatches > 0
        wrong_projects = project_mismatches > 0
        if wrong_count or wrong_transactions or wrong_employees or wrong_projects:
            raise ValueError("Foundations warehouse is stale; rerun its pipeline first")

        connection.commit()
    finally:

        connection.close()
    return database


def run_business_queries(connection):
    queries = read_sql_sections("queries.sql", ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"])
    results = {}

    for question, query in queries.items():
        result = pd.read_sql_query(query, connection)
        result.to_csv(OUT / (question.lower() + "_results.csv"), index=False)

        results[question] = result
        LOG.info("%s returned %d rows", question, len(result))
    return results


def measure_query(connection, query):
    connection.execute(query).fetchall()
    timings = []
    rows = []

    for repeat in range(7):
        start = time.perf_counter()

        rows = connection.execute(query).fetchall()
        elapsed_seconds = time.perf_counter() - start
        elapsed_milliseconds = elapsed_seconds * 1000
        timings.append(elapsed_milliseconds)
    measurement = {}
    measurement["median_ms"] = statistics.median(timings)

    measurement["rows"] = rows
    measurement["runs_ms"] = timings
    return measurement


def benchmark_queries(connection):
    """Compare timings and verify that optimisation preserves rows and duplicates."""
    sections = read_sql_sections(
        "query_optimization.sql", ["ORIGINAL", "INDEXES", "OPTIMIZED"]
    )
    original = sections["ORIGINAL"]
    optimized = sections["OPTIMIZED"]
    # EXPLAIN QUERY PLAN shows scan/search/index operations without inventing operator timings.
    original_plan = connection.execute("EXPLAIN QUERY PLAN " + original).fetchall()
    original_measurement = measure_query(connection, original)
    original_ms = original_measurement["median_ms"]
    original_rows = original_measurement["rows"]
    original_runs = original_measurement["runs_ms"]
    # Measure the rewrite before adding indexes so SQL and indexing gains are separate.
    rewrite_measurement = measure_query(connection, optimized)
    rewrite_ms = rewrite_measurement["median_ms"]
    rewrite_rows = rewrite_measurement["rows"]
    rewrite_runs = rewrite_measurement["runs_ms"]
    # Execute the index DDL only after timing the original and the unindexed rewrite.
    connection.executescript(sections["INDEXES"])
    optimized_plan = connection.execute("EXPLAIN QUERY PLAN " + optimized).fetchall()
    optimized_measurement = measure_query(connection, optimized)
    optimized_ms = optimized_measurement["median_ms"]
    optimized_rows = optimized_measurement["rows"]
    optimized_runs = optimized_measurement["runs_ms"]
    # Compare row contents and duplicate counts; ORDER BY ties can appear in any order.
    original_contents = Counter(original_rows)
    optimized_contents = Counter(optimized_rows)
    rewrite_contents = Counter(rewrite_rows)
    if original_contents != optimized_contents or original_contents != rewrite_contents:
        raise ValueError("Optimization changed query results")
    result = {}
    result["sqlite_version"] = sqlite3.sqlite_version
    result["row_count"] = len(original_rows)
    result["baseline_median_ms"] = original_ms
    result["rewrite_without_indexes_median_ms"] = rewrite_ms
    result["optimized_median_ms"] = optimized_ms

    result["speedup"] = original_ms / optimized_ms
    result["baseline_runs_ms"] = original_runs
    result["rewrite_runs_ms"] = rewrite_runs
    result["optimized_runs_ms"] = optimized_runs
    result["results_equal"] = True
    result["original_plan"] = original_plan
    result["optimized_plan"] = optimized_plan

    (OUT / "benchmark_results.json").write_text(json.dumps(result, indent=2) + "\n")
    # SQLite has EXPLAIN QUERY PLAN, not PostgreSQL's EXPLAIN ANALYZE operator timings.
    comments = [
        "-- MEASURED BENCHMARK (generated; see benchmark_results.json for all runs)",
        "-- SQLite "
        + sqlite3.sqlite_version
        + ": EXPLAIN QUERY PLAN + wall-clock timing.",
        "-- SQLite does not support EXPLAIN ANALYZE; no invented per-operator timings.",
        "-- Seven warm runs; median includes complete result fetching; automatic_index ON.",
        f"-- Original: {original_ms:.3f} ms; rewrite without indexes: {rewrite_ms:.3f} ms.",
        f"-- Optimized with indexes: {optimized_ms:.3f} ms; speedup {original_ms / optimized_ms:.2f}x.",
        f"-- Equivalent result multisets: True ({len(original_rows)} rows).",
        "-- ORIGINAL EXPLAIN QUERY PLAN:",
    ]

    for plan_row in original_plan:
        comments.append("-- " + str(plan_row))
    comments.append("-- OPTIMIZED EXPLAIN QUERY PLAN:")

    for plan_row in optimized_plan:
        comments.append("-- " + str(plan_row))
    comments += [
        "-- ANALYSIS: the baseline scans transactions for its main query and pending AVG.",
        "-- Indexed version uses payment_status equality and amount range to reduce transaction reads.",
        "-- Project/employee equality joins use ID indexes; ORDER BY still needs a temporary B-tree.",
        "-- Plans do not expose operator costs, so no exact most-expensive operator is claimed.",
        "-- No correlated subquery exists here: the scalar AVG has no reference to outer rows.",
        "-- SELECT time includes sorting/fetching, which indexes cannot eliminate in this ordering.",
        "-- A 10x gain is not guaranteed: data selectivity, automatic indexes and warm caches matter.",
        "-- Original/rewrite timings and actual index names are recorded above; no synthetic slowdown.",
    ]
    # Remove the previous generated report before appending new evidence, avoiding report accumulation.
    sql_text = (
        (HERE / "query_optimization.sql").read_text().split("-- MEASURED BENCHMARK")[0]
    )
    (HERE / "query_optimization.sql").write_text(
        sql_text.rstrip() + "\n\n" + "\n".join(comments) + "\n"
    )
    LOG.info(
        "Query speedup %.2fx: %.2f -> %.2f ms",
        result["speedup"],
        original_ms,
        optimized_ms,
    )
    return result


def save_cleaned_csvs(projects, employees, transactions):
    projects.to_csv(OUT / "projects_clean.csv", index=False)
    employees.to_csv(OUT / "employees_clean.csv", index=False)
    transactions.to_csv(OUT / "transactions_clean.csv", index=False)


def write_summary(projects, employees, transactions, before_counts, elapsed, benchmark):
    null_amounts = int(transactions["amount"].isna().sum())
    missing_approvers = int(transactions["approved_by"].isna().sum())

    summary = [
        "Pillar 2 ETL pipeline summary",
        "Run timestamp: " + datetime.now(ZoneInfo("Asia/Dubai")).isoformat(),
        f'Projects before/after: {before_counts["projects"]}/{len(projects)}',
        f'Employees before/after: {before_counts["employees"]}/{len(employees)}',
        f'Transactions before/after: {before_counts["transactions"]}/{len(transactions)}',
        f"Execution time (complete ETL, warehouse, SQL, benchmark, dashboard, CSV export): {elapsed:.3f} seconds",
        "Null source amount preserved; amount_aed uses 0.0 for reporting: "
        + str(null_amounts),
        "Missing approved_by preserved; name Unknown approver; is_approved False: "
        + str(missing_approvers),
        "Current employee names used for enrichment; historical versions remain in warehouse facts.",
        "All source currencies validated as AED; amount_aed does not perform FX conversion.",
        "LEFT joins validated many-to-one; no transaction loss or duplication.",
        "Foundation cleaning decisions: see 01_foundations/quality_summary.json and README.",
        "Date errors or unknown project references fail explicitly; no silent date replacement.",
        f'Query optimization: {benchmark["speedup"]:.2f}x; results equal: {benchmark["results_equal"]}',
        "SQL NULL amounts excluded by SUM/AVG; SQL shares and financial issues use AED facts.",
        "Dashboard is the permitted static, annotated PDF mockup; slicers are design controls.",
        "SQLite uses NUMERIC affinity for DECIMAL; exact financial arithmetic is not guaranteed.",
    ]

    (OUT / "pipeline_summary.txt").write_text("\n".join(summary) + "\n")


def run_pipeline():
    start = time.perf_counter()

    OUT.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    foundation_files = [
        "foundations.sqlite",
        "projects_clean.csv",
        "employees_clean.csv",
    ]
    missing_foundation_files = False

    for filename in foundation_files:
        if not (FOUNDATION_OUTPUT / filename).exists():
            missing_foundation_files = True
    if missing_foundation_files:

        sys.path.insert(0, str(FOUNDATIONS))
        import etl_pipeline as foundations

        foundations.run_pipeline()

    projects = pd.read_csv(FOUNDATION_OUTPUT / "projects_clean.csv")
    employees = pd.read_csv(FOUNDATION_OUTPUT / "employees_clean.csv")

    raw_transactions = load_transactions(DATA / "transactions.json")
    transactions = enrich_transactions(raw_transactions, projects, employees)

    raw_projects = pd.read_csv(DATA / "projects.csv")
    raw_employees = pd.read_csv(DATA / "employees.csv")
    before_counts = {}
    before_counts["projects"] = len(raw_projects)
    before_counts["employees"] = len(raw_employees)
    before_counts["transactions"] = len(raw_transactions)

    database = prepare_warehouse(projects, employees, raw_transactions)

    connection = sqlite3.connect(database)
    try:

        results = run_business_queries(connection)

        benchmark = benchmark_queries(connection)

        from dashboard import create_dashboard

        create_dashboard(connection, projects, results, OUT)
    finally:

        connection.close()

    save_cleaned_csvs(projects, employees, transactions)
    elapsed = time.perf_counter() - start

    write_summary(projects, employees, transactions, before_counts, elapsed, benchmark)
    LOG.info("Pipeline completed in %.3f seconds; output: %s", elapsed, OUT)

    if elapsed >= 30:
        LOG.warning("Measured full run exceeded the assessment 30-second target")


if __name__ == "__main__":
    run_pipeline()
