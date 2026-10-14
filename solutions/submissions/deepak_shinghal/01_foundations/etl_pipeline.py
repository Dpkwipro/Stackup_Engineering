"""Clean projects/employees and load the SCD2 warehouse (Tasks 1.1–1.3)."""

from pathlib import Path
import json
import logging
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]

OUT = ROOT / "outputs/results/deepak_shinghal/01_foundations"
DATA = ROOT / "datasets"
# Fixed export boundary after the last salary event (2025-06-30), not today's date.
AS_OF = pd.Timestamp("2025-07-01")

LOG = logging.getLogger(__name__)

SALARY_BANDS = {
    "Junior": (12000, 17000),
    "Mid": (17000, 24000),
    "Senior": (25000, 36000),
    "Lead": (38000, 50000),
    "Director": (50000, 70000),
}
# Experience is measured in years. These ranges guide detection, not factual recovery.
EXPERIENCE_BANDS = {
    "Junior": (0, 3),
    "Mid": (2, 6),
    "Senior": (5, 12),
    "Lead": (8, 18),
    "Director": (12, 45),
}


def load_projects(filepath):
    df = pd.read_csv(
        filepath, dtype={"project_id": "string", "project_manager_id": "string"}
    )

    df["start_date"] = pd.to_datetime(
        df["start_date"], format="%Y-%m-%d", errors="coerce"
    )
    df["end_date"] = pd.to_datetime(df["end_date"], format="%Y-%m-%d", errors="coerce")

    df["budget"] = pd.to_numeric(df["budget"], errors="coerce").astype("Float64")
    df["actual_cost"] = pd.to_numeric(df["actual_cost"], errors="coerce").astype(
        "Float64"
    )
    return df


def transform_projects(df):
    df = df.copy()

    df["budget"] = df["budget"].fillna(0)
    df["actual_cost"] = df["actual_cost"].fillna(0)

    df["status"] = df["status"].str.strip().str.title()
    df["priority"] = df["priority"].str.strip().str.title()

    df["budget_variance"] = df["actual_cost"] - df["budget"]

    df["is_over_budget"] = df["actual_cost"] > df["budget"]

    df["duration_days"] = (df["end_date"] - df["start_date"]).dt.days.astype("Int64")

    # Only calculate the percentage when the budget is not zero.
    df["budget_utilisation_pct"] = pd.Series(pd.NA, index=df.index, dtype="Float64")

    has_budget = df["budget"] != 0
    df.loc[has_budget, "budget_utilisation_pct"] = (
        df.loc[has_budget, "actual_cost"] / df.loc[has_budget, "budget"] * 100
    )

    status_categories = {
        "In Progress": "Active",
        "Completed": "Closed",
        "Not Started": "Pending",
        "On Hold": "Pending",
    }

    df["status_category"] = df["status"].map(status_categories)

    # Start with Low. Apply Medium, then High so High takes priority.
    df["risk_level"] = "Low"

    medium_risk = (df["priority"] == "High") | (df["budget_utilisation_pct"] > 90)
    df.loc[medium_risk.fillna(False), "risk_level"] = "Medium"

    high_risk = (df["priority"] == "Critical") | df["is_over_budget"]
    df.loc[high_risk, "risk_level"] = "High"
    return df


def load_employees(filepath):
    df = pd.read_csv(filepath)

    LOG.info("Employees: %d rows; null counts: %s", len(df), df.isna().sum().to_dict())
    return df


def record_issue(df, quality_report, issue_name, affected_rows, action):
    affected_rows = affected_rows.fillna(False)

    row_count = int(affected_rows.sum())

    employee_ids = df.loc[affected_rows, "employee_id"].tolist()

    quality_report.append(
        {
            "issue": issue_name,
            "rows_affected": row_count,
            "action": action,
            "employee_ids": employee_ids,
        }
    )
    LOG.info("%s: %d rows; %s", issue_name, row_count, action)


def fix_numeric_values(df, column_name, bands, quality_report):
    df[column_name] = pd.to_numeric(df[column_name], errors="coerce").astype("float64")

    minimum_by_level = {}
    maximum_by_level = {}

    for level_name, limits in bands.items():
        minimum_by_level[level_name] = limits[0]
        maximum_by_level[level_name] = limits[1]

    minimum = df["level"].map(minimum_by_level)
    maximum = df["level"].map(maximum_by_level)

    invalid = (
        df[column_name].isna()
        | (df[column_name] < minimum)
        | (df[column_name] > maximum)
    )
    record_issue(
        df,
        quality_report,
        column_name + "_out_of_range",
        invalid,
        "Impute median of valid peers at same level",
    )

    valid_employees = df.loc[~invalid]
    # The median is the middle valid peer value; for an even-sized group it averages the middle two.
    median_by_level = valid_employees.groupby("level")[column_name].median()

    replacement_values = df.loc[invalid, "level"].map(median_by_level)
    df.loc[invalid, column_name] = replacement_values


def clean_employees(df):
    df = df.copy()

    quality_report = []

    text_columns = df.select_dtypes(include=["object", "string"]).columns

    for column_name in text_columns:
        df[column_name] = df[column_name].astype("string").str.strip()
        df[column_name] = df[column_name].replace("", pd.NA)

    required_columns = [
        "employee_id",
        "full_name",
        "department",
        "role",
        "level",
        "status",
    ]
    for column_name in required_columns:
        missing = df[column_name].isna()
        record_issue(
            df,
            quality_report,
            "missing_" + column_name,
            missing,
            "Reject missing required identifiers/attributes",
        )

        if missing.any():
            raise ValueError("Missing required column value: " + column_name)

    missing_email = df["email"].isna()
    record_issue(
        df, quality_report, "missing_email", missing_email, "Set unknown@presight.ai"
    )
    df.loc[missing_email, "email"] = "unknown@presight.ai"

    email_pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    invalid_email = ~df["email"].str.match(email_pattern)
    record_issue(
        df, quality_report, "invalid_email", invalid_email, "Set unknown@presight.ai"
    )
    df.loc[invalid_email, "email"] = "unknown@presight.ai"

    raw_dates = df["hire_date"].copy()
    parsed_dates = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce")
    invalid_date = parsed_dates.isna()
    record_issue(
        df, quality_report, "invalid_hire_date", invalid_date, "Set unknown date (null)"
    )

    year_text = raw_dates.str.split("-").str[0]
    year_number = pd.to_numeric(year_text, errors="coerce")
    # Dates before 1900 or after the export boundary are outside our assumed business range.
    implausible_date = (
        (year_number < 1900)
        | (year_number > AS_OF.year)
        | (parsed_dates > AS_OF)
        | (parsed_dates < pd.Timestamp("1900-01-01"))
    )
    record_issue(
        df,
        quality_report,
        "implausible_hire_date",
        implausible_date,
        "Set unknown date (null); overlaps invalid dates",
    )
    df["hire_date"] = parsed_dates
    df.loc[invalid_date | implausible_date, "hire_date"] = pd.NaT

    fix_numeric_values(df, "salary", SALARY_BANDS, quality_report)

    fix_numeric_values(df, "years_experience", EXPERIENCE_BANDS, quality_report)

    # Assessment assumption: mark Active employees with unknown hire dates
    status_conflict = (df["status"] == "Active") & df["hire_date"].isna()
    record_issue(
        df,
        quality_report,
        "active_without_valid_hire_date",
        status_conflict,
        "Set Inactive pending HR confirmation",
    )
    df.loc[status_conflict, "status"] = "Inactive"

    duplicate_id = df["employee_id"].duplicated(keep=False)
    record_issue(
        df, quality_report, "duplicate_employee_id", duplicate_id, "Reject duplicates"
    )
    if duplicate_id.any():
        raise ValueError("Duplicate employee IDs")

    df.attrs["quality_summary"] = quality_report
    return df


def build_employee_versions(employees, history):
    """Keep one current row per employee and non-overlapping historical periods."""
    salary_history = history.copy()

    salary_history["effective_date"] = pd.to_datetime(
        salary_history["effective_date"], format="%Y-%m-%d", errors="raise"
    )

    if not salary_history["employee_id"].isin(employees["employee_id"]).all():
        raise ValueError("Ambiguous or orphan history")

    if salary_history["effective_date"].ge(AS_OF).any():
        raise ValueError("History must precede snapshot boundary")
    # EMP0084 changes twice in one day; retain its final daily state for date-based history.
    LOG.info(
        "Same-day intermediate history events: %d",
        salary_history.duplicated(["employee_id", "effective_date"]).sum(),
    )
    # Sort by employee and date before deriving periods. stable preserves same-day source order.
    salary_history = salary_history.sort_values(
        ["employee_id", "effective_date"], kind="stable"
    )
    # keep="last" keeps the final same-day source event; this dataset orders raise before promotion.
    salary_history = salary_history.drop_duplicates(
        ["employee_id", "effective_date"], keep="last"
    )

    historical_versions = salary_history.merge(
        employees, on="employee_id", validate="many_to_one"
    )
    historical_versions["valid_from"] = historical_versions[
        "effective_date"
    ].dt.strftime("%Y-%m-%d")
    # shift(-1) gives the next event date within the same employee's group.
    next_change_date = historical_versions.groupby("employee_id")[
        "effective_date"
    ].shift(-1)
    # End each employee’s last historical version at the current-snapshot boundary.
    next_change_date = next_change_date.fillna(AS_OF)

    historical_versions["valid_to"] = next_change_date.dt.strftime("%Y-%m-%d")

    for col in ("salary", "role", "level"):
        historical_versions[col] = historical_versions["new_" + col]

    historical_versions["is_current"] = 0

    current = employees.copy()

    current["valid_from"] = (
        current["hire_date"].dt.strftime("%Y-%m-%d").fillna("1900-01-01")
    )

    current.loc[
        current["employee_id"].isin(salary_history["employee_id"]), "valid_from"
    ] = AS_OF.strftime("%Y-%m-%d")
    # 9999-12-31 is a sentinel meaning no known end; it is not a predicted termination date.
    current["valid_to"] = "9999-12-31"
    current["is_current"] = 1

    current["change_reason"] = "Current export snapshot"
    current.loc[current["hire_date"].isna(), "change_reason"] = (
        "Unknown hire date; lower-bound sentinel"
    )

    columns = employees.columns.tolist() + [
        "valid_from",
        "valid_to",
        "is_current",
        "change_reason",
    ]

    versions = pd.concat(
        [historical_versions[columns], current[columns]], ignore_index=True
    )
    versions = versions.sort_values(["employee_id", "valid_from"])

    versions = versions.reset_index(drop=True)

    versions.insert(0, "employee_key", range(1, len(versions) + 1))
    versions["hire_date"] = pd.to_datetime(versions["hire_date"]).dt.strftime(
        "%Y-%m-%d"
    )
    return versions


def load_warehouse(projects, employees):
    salary_history = pd.read_csv(DATA / "employees_salary_history.csv")
    versions = build_employee_versions(employees, salary_history)

    transactions = pd.read_json(DATA / "transactions.json")
    dates = pd.to_datetime(
        transactions["transaction_date"], format="%Y-%m-%d", errors="raise"
    )

    first_date = min(dates.min(), projects["start_date"].min())
    last_date = max(dates.max(), AS_OF)

    calendar = pd.Series(pd.date_range(first_date, last_date, freq="D"))
    dim_date = pd.DataFrame()

    dim_date["date_key"] = calendar.dt.strftime("%Y%m%d").astype(int)
    dim_date["full_date"] = calendar.dt.strftime("%Y-%m-%d")
    dim_date["year"] = calendar.dt.year
    dim_date["quarter"] = calendar.dt.quarter
    dim_date["month"] = calendar.dt.month
    dim_date["month_name"] = calendar.dt.month_name()

    dim_date["week"] = calendar.dt.isocalendar().week.astype(int)
    dim_date["day"] = calendar.dt.day

    dim_date["day_of_week"] = calendar.dt.dayofweek + 1

    dim_date["is_weekend"] = (calendar.dt.dayofweek >= 5).astype(int)

    project_columns = [
        "project_id",
        "project_name",
        "department",
        "status",
        "start_date",
        "end_date",
        "budget",
        "actual_cost",
        "project_manager_id",
        "priority",
        "region",
    ]
    project_dimension = projects[project_columns].copy()
    for col in ("start_date", "end_date"):
        project_dimension[col] = project_dimension[col].dt.strftime("%Y-%m-%d")

    project_dimension.insert(0, "project_key", range(1, len(project_dimension) + 1))

    vendors = transactions[["vendor_id", "vendor_name"]].drop_duplicates()

    if vendors["vendor_id"].duplicated().any():
        raise ValueError("Conflicting vendor names")
    vendors.insert(0, "vendor_key", range(1, len(vendors) + 1))
    database_path = OUT / "foundations.sqlite"

    if database_path.exists():
        database_path.unlink()

    connection = sqlite3.connect(database_path)
    try:

        connection.executescript(Path(__file__).with_name("data_model.sql").read_text())

        dim_date.to_sql("dim_date", connection, if_exists="append", index=False)
        project_dimension.to_sql(
            "dim_project", connection, if_exists="append", index=False
        )
        versions.to_sql("dim_employee", connection, if_exists="append", index=False)
        vendors.to_sql("dim_vendor", connection, if_exists="append", index=False)
        # Key 0 is the explicit unknown member. Real employee version keys start at 1.
        connection.execute(
            "INSERT INTO dim_employee(employee_key,employee_id,full_name,valid_from,valid_to,is_current,change_reason) VALUES(0,'UNKNOWN','Unknown approver','1900-01-01','9999-12-31',1,'Missing approver')"
        )
        transactions["transaction_date"] = dates.dt.strftime("%Y-%m-%d")

        transactions.to_sql("staging_transactions", connection, index=False)
        # Match the approver version where valid_from <= transaction date < valid_to.
        connection.execute("""INSERT INTO fact_transactions
          SELECT ROW_NUMBER() OVER (ORDER BY t.transaction_id), t.transaction_id,
            p.project_key, COALESCE(e.employee_key,0), v.vendor_key,
            CAST(REPLACE(t.transaction_date,'-','') AS INTEGER),
            t.amount,t.currency,t.category,t.payment_status,t.invoice_ref
          FROM staging_transactions t JOIN dim_project p USING(project_id)
          JOIN dim_vendor v USING(vendor_id)
          LEFT JOIN dim_employee e ON e.employee_id=t.approved_by
            AND t.transaction_date>=e.valid_from AND t.transaction_date<e.valid_to""")

        connection.execute(
            """INSERT INTO bridge_employee_project
          SELECT e.employee_key,p.project_key,'Manager' FROM dim_project p
          JOIN dim_employee e ON e.employee_id=p.project_manager_id AND e.is_current=1
          UNION SELECT employee_key,project_key,'Approver' FROM fact_transactions WHERE employee_key<>0"""
        )

        checks = {
            "duplicate_currents": "SELECT employee_id FROM dim_employee WHERE is_current=1 GROUP BY employee_id HAVING COUNT(*)>1",
            "missing_currents": "SELECT employee_id FROM dim_employee GROUP BY employee_id HAVING SUM(is_current)<>1",
            "overlapping_periods": "SELECT a.employee_id FROM dim_employee a JOIN dim_employee b ON a.employee_id=b.employee_id AND a.employee_key<b.employee_key AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to",
            "foreign_key_violations": "PRAGMA foreign_key_check",
            "historical_value_mismatches": "SELECT e.employee_key FROM dim_employee e JOIN staging_history h ON e.employee_id=h.employee_id AND e.valid_from=h.effective_date WHERE e.is_current=0 AND (e.salary<>h.new_salary OR e.role<>h.new_role OR e.level<>h.new_level)",
        }
        # keep="last" keeps the final same-day source event; this dataset orders raise before promotion.
        salary_history = salary_history.drop_duplicates(
            ["employee_id", "effective_date"], keep="last"
        )
        salary_history.to_sql("staging_history", connection, index=False)
        validation = {}

        for check_name, sql_query in checks.items():
            problem_rows = connection.execute(sql_query).fetchall()
            validation[check_name] = len(problem_rows)

            if len(problem_rows) > 0:
                raise ValueError("Warehouse validation failed: " + check_name)
        counts = {}
        tables = [
            "dim_project",
            "dim_employee",
            "dim_date",
            "dim_vendor",
            "bridge_employee_project",
            "fact_transactions",
        ]
        for table_name in tables:

            sql_query = "SELECT COUNT(*) FROM " + table_name

            result = connection.execute(sql_query).fetchone()
            counts[table_name] = result[0]

        if counts["fact_transactions"] != len(transactions):
            raise ValueError("Some transactions were lost or duplicated during loading")

        validation["version_history_top_10"] = connection.execute(
            "SELECT employee_id, COUNT(*) FROM dim_employee WHERE employee_key<>0 GROUP BY employee_id ORDER BY COUNT(*) DESC,employee_id LIMIT 10"
        ).fetchall()
        validation["table_counts"] = counts
        # Count all unknown assignments, including missing IDs and unmatched temporal versions.
        validation["unknown_approver_facts"] = connection.execute(
            "SELECT COUNT(*) FROM fact_transactions WHERE employee_key=0"
        ).fetchone()[0]

        validation["unmatched_nonnull_approvers"] = connection.execute(
            """SELECT COUNT(*) FROM fact_transactions f JOIN staging_transactions t USING(transaction_id) WHERE f.employee_key=0 AND t.approved_by IS NOT NULL"""
        ).fetchone()[0]

        connection.execute("DROP TABLE staging_transactions")
        connection.execute("DROP TABLE staging_history")

        connection.commit()
    finally:

        connection.close()

    versions.to_csv(OUT / "employee_versions.csv", index=False)
    return validation


def run_pipeline():
    OUT.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(OUT / "pipeline.log", mode="w"),
        ],
    )

    raw_projects = load_projects(DATA / "projects.csv")
    projects = transform_projects(raw_projects)

    raw_employees = load_employees(DATA / "employees.csv")
    employees = clean_employees(raw_employees)

    projects.to_csv(OUT / "projects_clean.csv", index=False)
    employees.to_csv(OUT / "employees_clean.csv", index=False)

    (OUT / "quality_summary.json").write_text(
        json.dumps(employees.attrs["quality_summary"], indent=2) + "\n"
    )

    validation = load_warehouse(projects, employees)

    (OUT / "validation_results.json").write_text(
        json.dumps(validation, indent=2) + "\n"
    )
    LOG.info(
        "Complete: projects=%d, employees=%d; warehouse=%s",
        len(projects),
        len(employees),
        validation,
    )


if __name__ == "__main__":
    run_pipeline()
