"""Check rule scores, CSV extension and boundary cases."""

import csv
from copy import deepcopy
import pandas as pd
import pytest
from data_quality import (
    CONFIG_COLUMNS,
    load_rules,
    run_data_quality_checks,
    write_dq_report,
)


def rule(identifier, dimension, column, condition):
    return dict(
        zip(
            CONFIG_COLUMNS,
            [identifier, identifier + " check", "sample", column, dimension, condition],
        )
    )


def run(table, rules, tables=None, date="2025-01-31"):
    return run_data_quality_checks(
        table, "sample", tables=tables, config=rules, as_of=date
    )


def test_all_six_dimensions_scores_and_warnings(caplog):
    table = pd.DataFrame(
        {
            "id": ["1", "1", None, "4"],
            "amount": [10, 20, -1, None],
            "date": ["2025-01-01", "bad", "2025-02-01", "2025-01-02"],
            "end": ["2025-01-02", "2025-01-01", "2025-01-01", "2025-01-03"],
            "parent": ["P1", "P9", None, "P1"],
        }
    )
    rules = [
        rule("R1", "completeness", "id", "not_null; score >= 80%"),
        rule("R2", "uniqueness", "id", "unique"),
        rule("R3", "numeric_validity", "amount", "between 0 and 100; allow_null"),
        rule("R4", "date_validity", "date", "not_future"),
        rule("R5", "consistency", "date", "before end"),
        rule(
            "R6", "referential_integrity", "parent", "exists in parents.id; allow_null"
        ),
    ]
    original = table.copy(deep=True)
    report = run(table, rules, {"parents": pd.DataFrame({"id": ["P1"]})})
    expected = {"R1": 75, "R2": 25, "R3": 66.67, "R4": 50, "R5": 50, "R6": 66.67}
    assert {
        key: value["score_pct"] for key, value in report["results"].items()
    } == expected
    assert report["checks_failed"] == 6
    assert (
        len([record for record in caplog.records if record.levelname == "WARNING"]) == 6
    )
    pd.testing.assert_frame_equal(table, original)


def test_thresholds_blanks_and_optional_nulls():
    table = pd.DataFrame({"id": ["A", " ", None, "B"]})
    rules = [
        rule("R1", "completeness", "id", "not_null; score >= 50%"),
        rule("R2", "uniqueness", "id", "unique; allow_null"),
    ]
    report = run(table, rules)
    assert report["checks_passed"] == 2
    assert report["results"]["R2"]["checked_rows"] == 2
    rules[0]["condition"] = "not_null; score >= 50.01%"
    assert run(table, rules)["results"]["R1"]["status"] == "FAIL"


def test_conditional_salary_role_and_no_applicable_rows():
    table = pd.DataFrame(
        {
            "salary": [12000, 30000],
            "level": ["Junior", "Junior"],
            "role": ["Analyst", "Senior Analyst"],
        }
    )
    rules = [
        rule(
            "R1", "consistency", "salary", "between 10000 and 15000 when level = Junior"
        ),
        rule(
            "R2", "consistency", "level", "equals Senior when role starts_with Senior"
        ),
        rule(
            "R3", "consistency", "salary", "between 30000 and 50000 when level = Lead"
        ),
    ]
    report = run(table, rules)
    assert report["results"]["R1"]["score_pct"] == 50
    assert report["results"]["R2"]["score_pct"] == 0
    assert report["results"]["R3"]["score_pct"] is None
    assert report["checks_not_applicable"] == 1


def test_composite_uniqueness_missing_columns_and_reference():
    table = pd.DataFrame({"id": ["1", "1"], "amount": [10, 20]})
    rules = [
        rule("R1", "uniqueness", "id|amount", "unique"),
        rule("R2", "date_validity", "absent", "valid_date"),
        rule("R3", "referential_integrity", "id", "exists in missing.id"),
    ]
    report = run(table, rules)
    assert report["results"]["R1"]["score_pct"] == 100
    assert (
        report["results"]["R2"]["status"] == report["results"]["R3"]["status"] == "FAIL"
    )
    table.loc[1, "amount"] = 10
    assert run(table, rules)["results"]["R1"]["score_pct"] == 0


def test_freshness_boundary_future_and_invalid_dates():
    rules = [rule("R1", "freshness", "date", "max_date within 30 days")]
    for date, status in [
        ("2025-01-01", "PASS"),
        ("2024-12-31", "FAIL"),
        ("2025-02-01", "FAIL"),
        ("bad", "FAIL"),
    ]:
        result = run(pd.DataFrame({"date": [date]}), rules)["results"]["R1"]
        assert result["checked_rows"] == 1 and result["status"] == status
    assert (
        run(pd.DataFrame({"date": ["2025-01-30", "bad"]}), rules)["checks_failed"] == 1
    )


def test_distribution_strictly_above_30_percent():
    rules = [rule("R1", "distribution", "amount", "most_common_share <= 30%")]
    table = pd.DataFrame({"amount": [1, 1, 1, 2, 3, 4, 5, 6, 7, 8, None]})
    assert run(table, rules)["checks_passed"] == 1
    table.loc[9, "amount"] = 1
    assert run(table, rules)["results"]["R1"]["score_pct"] == 0
    assert run(pd.DataFrame({"amount": [None]}), rules)["checks_not_applicable"] == 1


def test_add_csv_rule_without_changing_runner(tmp_path):
    path = tmp_path / "rules.csv"
    rules = [rule("R1", "completeness", "id", "not_null")]

    def save():
        with path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CONFIG_COLUMNS)
            writer.writeheader()
            writer.writerows(rules)

    table = pd.DataFrame({"id": ["1", "2"], "amount": [0, -1]})
    save()
    assert run(table, load_rules(path))["checks_run"] == 1
    rules.append(rule("R2", "consistency", "amount", "non_negative"))
    save()
    report = run(table, load_rules(path))
    assert report["checks_run"] == 2 and report["results"]["R2"]["score_pct"] == 50
    write_dq_report(report, tmp_path)
    output = pd.read_csv(tmp_path / "dq_scores_sample.csv")
    assert output["score_pct"].tolist() == [100, 50]
    assert "| R2 |" in (tmp_path / "dq_report_sample.md").read_text()


def test_config_errors_are_not_executed_or_silently_ignored(tmp_path):
    base = rule("R1", "numeric_validity", "amount", "between 0 and 100")
    for condition in [
        "between 100 and 0",
        "between 0 and 100; score >= 101%",
        '__import__("os")',
        "not_null",
    ]:
        item = deepcopy(base)
        item["condition"] = condition
        path = tmp_path / "rules.csv"
        pd.DataFrame([item]).to_csv(path, index=False)
        with pytest.raises(ValueError):
            load_rules(path)
    pd.DataFrame([base, base]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="unique"):
        load_rules(path)


def test_empty_sources_do_not_claim_success():
    report = run(
        pd.DataFrame({"id": []}),
        [
            rule("R1", "completeness", "id", "not_null"),
            rule("R2", "uniqueness", "id", "unique"),
        ],
    )
    assert report["checks_failed"] == 2
