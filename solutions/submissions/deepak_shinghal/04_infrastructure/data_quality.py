"""Run CSV-configured quality rules and write scores for Task 4.3."""

import json
import logging
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
CONFIG_FILE = Path(__file__).with_name("rule_config.csv")
LOG = logging.getLogger(__name__)
CONFIG_COLUMNS = [
    "rule_id",
    "rule_name",
    "tablename",
    "column",
    "dimension",
    "condition",
]
ALLOWED_CHECKS = {
    "completeness": ["not_null"],
    "uniqueness": ["unique"],
    "numeric_validity": ["between"],
    "date_validity": ["valid_date", "not_future"],
    "consistency": ["before", "non_negative", "between", "equals"],
    "referential_integrity": ["exists"],
    "freshness": ["max_date"],
    "distribution": ["most_common_share"],
}


def read_condition(rule):
    """Turn the CSV text into named settings, without executing it as code."""
    parts = rule["condition"].split(";")
    settings = {"threshold": 100.0, "allow_null": False}
    for option in parts[1:]:
        option = option.strip()
        if option == "allow_null":
            settings["allow_null"] = True
        elif option.startswith("score >= ") and option.endswith("%"):
            settings["threshold"] = float(
                option.removeprefix("score >= ").removesuffix("%")
            )
        else:
            raise ValueError("Unknown rule option: " + option)
    if not 0 <= settings["threshold"] <= 100:
        raise ValueError("Score threshold must be 0–100")

    condition = parts[0].strip()
    if " when " in condition:
        condition, filter_text = condition.split(" when ", 1)
        if " = " in filter_text:
            settings["filter_column"], settings["filter_value"] = filter_text.split(
                " = ", 1
            )
            settings["filter_type"] = "equals"
        elif " starts_with " in filter_text:
            settings["filter_column"], settings["filter_value"] = filter_text.split(
                " starts_with ", 1
            )
            settings["filter_type"] = "starts_with"
        else:
            raise ValueError("Unknown filter: " + filter_text)

    words = condition.split()
    check = words[0]
    settings["check"] = check
    if check not in ALLOWED_CHECKS.get(rule["dimension"], []):
        raise ValueError("Unsupported dimension/condition: " + rule["condition"])

    if check == "between":
        if len(words) != 4 or words[2] != "and":
            raise ValueError("Use: between minimum and maximum")
        settings["minimum"] = float(words[1])
        settings["maximum"] = float(words[3])
        if settings["minimum"] > settings["maximum"]:
            raise ValueError("Minimum exceeds maximum")
    elif check == "before":
        settings["other_column"] = condition.removeprefix("before ")
    elif check == "equals":
        settings["expected_value"] = condition.removeprefix("equals ")
        if "filter_column" not in settings:
            raise ValueError("An equals rule needs a when condition")
    elif check == "exists":
        reference = condition.removeprefix("exists in ")
        settings["reference_table"], settings["reference_column"] = reference.split(".")
    elif check == "max_date":
        days = condition.removeprefix("max_date within ").removesuffix(" days")
        settings["days"] = int(days)
        if settings["days"] < 0:
            raise ValueError("Freshness days cannot be negative")
    elif check == "most_common_share":
        limit = condition.removeprefix("most_common_share <= ").removesuffix("%")
        settings["limit"] = float(limit)
        if not 0 <= settings["limit"] <= 100:
            raise ValueError("Distribution limit must be 0–100")
    elif condition != check:
        raise ValueError("Unsupported condition: " + condition)

    if "filter_column" in settings and rule["dimension"] != "consistency":
        raise ValueError("Use when conditions only for consistency rules")
    return settings


def load_rules(path=CONFIG_FILE):
    # One CSV row becomes one rule dictionary.
    rules = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(rules.columns) != CONFIG_COLUMNS:
        raise ValueError("Rule CSV columns must be: " + ",".join(CONFIG_COLUMNS))
    for column in rules.columns:
        rules[column] = rules[column].str.strip()
    if rules.empty or (rules == "").any().any():
        raise ValueError("The config must have rules with all six fields filled")
    if rules["rule_id"].duplicated().any():
        raise ValueError("Each rule_id must be unique")
    records = rules.to_dict("records")
    for rule in records:
        try:
            read_condition(rule)
        except (ValueError, IndexError) as error:
            raise ValueError(f"{rule['rule_id']}: {error}") from error
    return records


def check_rule(table, rule, tables, today):
    settings = read_condition(rule)
    check = settings["check"]
    threshold = settings["threshold"]
    columns = rule["column"].split("|")
    for column in columns:
        if column not in table:
            raise KeyError("Missing column: " + column)
    values = table[columns[0]]
    eligible = pd.Series(True, index=table.index)
    details = ""
    dimension = rule["dimension"]

    # Optional missing values are excluded from the score denominator.
    if settings["allow_null"]:
        eligible = table[columns].notna().all(axis=1)
    if "filter_column" in settings:
        filter_values = table[settings["filter_column"]]
        if settings["filter_type"] == "equals":
            matches = filter_values.eq(settings["filter_value"])
        else:
            matches = filter_values.astype("string").str.startswith(
                settings["filter_value"], na=False
            )
        eligible = eligible & matches

    if dimension == "completeness":
        eligible[:] = True
        passed = table[columns].notna().all(axis=1)
    elif dimension == "uniqueness":
        # Every occurrence of a duplicate key fails, including its first occurrence.
        passed = table[columns].notna().all(axis=1) & ~table.duplicated(
            columns, keep=False
        )
    elif dimension == "numeric_validity":
        numbers = pd.to_numeric(values, errors="coerce")
        passed = numbers.between(settings["minimum"], settings["maximum"])
    elif dimension == "date_validity":
        dates = pd.to_datetime(values, format="%Y-%m-%d", errors="coerce")
        passed = dates.notna()
        if check == "not_future":
            passed = passed & (dates <= today)
    elif dimension == "consistency":
        if check == "before":
            other = table[settings["other_column"]]
            if settings["allow_null"]:
                eligible = eligible & other.notna()
            first = pd.to_datetime(values, format="%Y-%m-%d", errors="coerce")
            last = pd.to_datetime(other, format="%Y-%m-%d", errors="coerce")
            passed = first.notna() & last.notna() & (first < last)
        elif check == "non_negative":
            passed = pd.to_numeric(values, errors="coerce") >= 0
        elif check == "between":
            numbers = pd.to_numeric(values, errors="coerce")
            passed = numbers.between(settings["minimum"], settings["maximum"])
        else:
            passed = values.eq(settings["expected_value"])
    elif dimension == "referential_integrity":
        reference = tables[settings["reference_table"]][
            settings["reference_column"]
        ].replace(r"^\s*$", pd.NA, regex=True)
        passed = values.notna() & values.isin(reference.dropna())
    elif dimension == "freshness":
        # Freshness and distribution are one dataset-level test, not one test per row.
        dates = pd.to_datetime(values, format="%Y-%m-%d", errors="coerce")
        if not dates.notna().any():
            return 1, 0, threshold, "No usable dates; freshness cannot be established"
        latest = dates.max()
        age = (today - latest).days
        invalid = int((values.notna() & dates.isna()).sum())
        details = f"Latest date: {latest.date()}; age: {age} days; limit: {settings['days']} days; invalid dates: {invalid}"
        success = 0 <= age <= settings["days"] and invalid == 0
        return 1, int(success), threshold, details
    else:
        counts = values.dropna().value_counts()
        if counts.empty:
            return 0, 0, threshold, "No non-null values to measure"
        share = float(counts.iloc[0] / counts.sum() * 100)
        details = f"Most common share: {share:.2f}%; limit: {settings['limit']:g}%; non-null rows: {int(counts.sum())}"
        return 1, int(share <= settings["limit"]), threshold, details

    checked = int(eligible.sum())
    passed_count = int((passed.fillna(False) & eligible).sum())
    details = f"Total rows: {len(table)}; excluded rows: {len(table) - checked}"
    return checked, passed_count, threshold, details


def run_data_quality_checks(df, dataset_name, tables=None, config=None, as_of=None):
    if config is None:
        config = load_rules()
    if tables is None:
        tables = {}
    if as_of is None:
        as_of = pd.Timestamp.now(tz="Asia/Dubai").date()
    today = pd.Timestamp(as_of)
    table = df.replace(r"^\s*$", pd.NA, regex=True)
    results = {}
    # Run each rule, then calculate its score from the counts.
    for rule in config:
        if rule["tablename"] != dataset_name:
            continue
        threshold = read_condition(rule)["threshold"]
        try:
            checked, passed, threshold, details = check_rule(table, rule, tables, today)
            score = None
            status = "NOT APPLICABLE"
            if checked > 0:
                score = passed / checked * 100
                status = "PASS"
                if score < threshold:
                    status = "FAIL"
        except KeyError as error:
            checked, passed, score, status = 0, 0, None, "FAIL"
            details = "Missing column or reference table: " + str(error)
        # An empty source must not claim that its completeness/keys passed.
        if table.empty and rule["dimension"] in ["completeness", "uniqueness"]:
            score, status, details = 0.0, "FAIL", "Source table has no rows"
        displayed_score = None
        if score is not None:
            displayed_score = round(score, 2)
        results[rule["rule_id"]] = {
            "rule_name": rule["rule_name"],
            "column": rule["column"],
            "dimension": rule["dimension"],
            "condition": rule["condition"],
            "checked_rows": checked,
            "passed_rows": passed,
            "failed_rows": checked - passed,
            "score_pct": displayed_score,
            "threshold_pct": threshold,
            "status": status,
            "details": details,
        }
        if status == "FAIL":
            LOG.warning(
                "%s %s (%s): FAIL; score=%s; %s",
                dataset_name,
                rule["rule_id"],
                rule["rule_name"],
                score,
                details,
            )
    if not results:
        raise ValueError("No configured rules for " + dataset_name)
    passed = 0
    failed = 0
    for result in results.values():
        if result["status"] == "PASS":
            passed += 1
        elif result["status"] == "FAIL":
            failed += 1
    return {
        "dataset_name": dataset_name,
        "checks_run": len(results),
        "checks_passed": passed,
        "checks_failed": failed,
        "checks_not_applicable": len(results) - passed - failed,
        "results": results,
    }


def write_dq_report(report, output_dir):
    # Save the same results as a readable markdown table and a CSV.
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data quality: " + report["dataset_name"],
        "",
        "| Rule | Name | Dimension | Checked | Passed | Failed | Score | Status |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    rows = []
    for identifier, result in report["results"].items():
        score = "N/A"
        if result["score_pct"] is not None:
            score = str(result["score_pct"]) + "%"
        name = result["rule_name"].replace("|", "\\|")
        lines.append(
            f"| {identifier} | {name} | {result['dimension']} | {result['checked_rows']} | {result['passed_rows']} | {result['failed_rows']} | {score} | {result['status']} |"
        )
        row = result.copy()
        row["rule_id"] = identifier
        row["tablename"] = report["dataset_name"]
        rows.append(row)
    lines.extend(["", "## Details", ""])
    for identifier, result in report["results"].items():
        lines.append(f"- {identifier}: {result['details']}")
    path = folder / ("dq_report_" + report["dataset_name"] + ".md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(
        folder / ("dq_scores_" + report["dataset_name"] + ".csv"), index=False
    )
    return path


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    data_dir = Path(os.environ.get("DATA_DIR", ROOT / "datasets"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs"))
    output_dir = output_dir / "results/deepak_shinghal/04_infrastructure"
    rules = load_rules(os.environ.get("DQ_CONFIG_FILE", CONFIG_FILE))
    tables = {}
    names = []
    scored_tables = []
    for rule in rules:
        names.append(rule["tablename"])
        if rule["tablename"] not in scored_tables:
            scored_tables.append(rule["tablename"])
        if rule["dimension"] == "referential_integrity":
            names.append(read_condition(rule)["reference_table"])
    for name in names:
        if name not in tables:
            path = data_dir / (name + ".csv")
            if path.exists():
                tables[name] = pd.read_csv(path)
            else:
                tables[name] = pd.read_json(data_dir / (name + ".json"))
    reports = {}
    for name, table in tables.items():
        if name not in scored_tables:
            continue
        report = run_data_quality_checks(table, name, tables, rules)
        reports[name] = report
        write_dq_report(report, output_dir)
        print(
            f"{name}: {report['checks_run']} rules; {report['checks_passed']} passed; {report['checks_failed']} failed"
        )
    (output_dir / "dq_results.json").write_text(json.dumps(reports, indent=2) + "\n")
    print("Reports saved to", output_dir)


if __name__ == "__main__":
    main()
