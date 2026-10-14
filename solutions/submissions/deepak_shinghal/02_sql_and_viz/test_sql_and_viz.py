"""Tests for the 02 sql and viz solution."""

from contextlib import closing
import json
import sqlite3
import unittest
import pandas as pd
from etl_full import (
    HERE,
    OUT,
    FOUNDATION_OUTPUT,
    read_sql_sections,
    enrich_transactions,
)

QUERIES = read_sql_sections("queries.sql", ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"])


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        schema = (HERE.parent / "01_foundations/data_model.sql").read_text()
        self.connection.executescript(schema)

    def tearDown(self):
        self.connection.close()

    def employee(self, key, identifier, salary, start, end, current):
        self.connection.execute(
            """INSERT INTO dim_employee
          (employee_key,employee_id,full_name,email,salary,valid_from,valid_to,is_current)
          VALUES(?,?,?, ?,?,?,?,?)""",
            (
                key,
                identifier,
                identifier + " Name",
                identifier + "@test.ai",
                salary,
                start,
                end,
                current,
            ),
        )

    def project(self, key, department, budget, cost, manager="E1"):
        self.connection.execute(
            """INSERT INTO dim_project
          (project_key,project_id,project_name,department,status,budget,actual_cost,project_manager_id)
          VALUES(?,?,?,?,'In Progress',?,?,?)""",
            (
                key,
                "P" + str(key),
                "Project " + str(key),
                department,
                budget,
                cost,
                manager,
            ),
        )

    def date(self, key, text):
        self.connection.execute(
            """INSERT INTO dim_date VALUES(?,?,2024,1,1,'January',1,1,1,0)""",
            (key, text),
        )

    def vendor(self, key, name):
        self.connection.execute(
            "INSERT INTO dim_vendor VALUES(?,?,?)", (key, "V" + str(key), name)
        )

    def fact(self, key, date, vendor, amount, status="Pending", currency="AED"):
        self.connection.execute(
            """INSERT INTO fact_transactions
          (transaction_key,transaction_id,project_key,employee_key,vendor_key,date_key,amount,currency,category,payment_status)
          VALUES(?,?,1,1,?,?,?,?, 'Software',?)""",
            (key, "T" + str(key), vendor, date, amount, currency, status),
        )

    def test_budget_threshold_and_zero_denominator(self):
        self.project(1, "Exactly90", 100, 90)
        self.project(2, "Above90", 100, 91)
        self.project(3, "Overspent", 100, 120)
        self.project(4, "ZeroBudget", 0, 10)
        result = pd.read_sql_query(QUERIES["Q1"], self.connection)
        self.assertEqual(result.department.tolist(), ["Overspent", "Above90"])
        self.assertEqual(result.over_budget.tolist(), [1, 0])

    def test_current_manager_only_and_strictly_more_than_three(self):
        self.employee(1, "E1", 100, "2020-01-01", "2024-01-01", 0)
        self.employee(2, "E1", 120, "2024-01-01", "9999-12-31", 1)
        for key in range(1, 4):
            self.project(key, "Finance", 100, 90)
        self.assertTrue(pd.read_sql_query(QUERIES["Q2"], self.connection).empty)
        self.project(4, "Finance", 100, 90)
        result = pd.read_sql_query(QUERIES["Q2"], self.connection)
        self.assertEqual(result.active_project_count.tolist(), [4])
        self.assertEqual(result.combined_budget_responsibility.tolist(), [400])

    def test_vendor_identity_and_risk_boundaries(self):
        self.employee(1, "E1", 100, "2020-01-01", "9999-12-31", 1)
        self.project(1, "Finance", 100, 90)
        self.date(20240101, "2024-01-01")
        for key, name, amount in [
            (1, "Shared name", 60),
            (2, "Shared name", 120),
            (3, "Exactly5", 50),
            (4, "Exactly10", 100),
            (5, "Rest", 670),
        ]:
            self.vendor(key, name)
            self.fact(key, 20240101, key, amount)
        result = pd.read_sql_query(QUERIES["Q3"], self.connection)
        self.assertEqual(len(result[result.vendor_name == "Shared name"]), 2)
        self.assertNotIn("Exactly5", result.vendor_name.tolist())
        self.assertEqual(
            result.loc[result.vendor_name == "Exactly10", "risk_flag"].iloc[0], "MEDIUM"
        )
        self.assertEqual(
            result.loc[result.total_spend == 120, "risk_flag"].iloc[0], "HIGH"
        )

    def test_open_issue_boundary_and_currency(self):
        self.employee(1, "E1", 100, "2020-01-01", "9999-12-31", 1)
        self.project(1, "Finance", 100, 90)
        self.date(20240101, "2024-01-01")
        self.vendor(1, "Vendor")
        self.fact(1, 20240101, 1, 50000)
        self.fact(2, 20240101, 1, 100000, currency="USD")
        self.fact(3, 20240101, 1, 100000, status="Paid")
        self.assertTrue(pd.read_sql_query(QUERIES["Q4"], self.connection).empty)
        self.fact(4, 20240101, 1, 1, status="Disputed")
        result = pd.read_sql_query(QUERIES["Q4"], self.connection)
        self.assertEqual(result.open_transaction_value.tolist(), [50001])
        self.assertEqual(result.open_transaction_count.tolist(), [2])

    def test_running_total_calendar_gap_and_zero_prior_month(self):
        self.employee(1, "E1", 100, "2020-01-01", "9999-12-31", 1)
        self.project(1, "Finance", 100, 90)
        for key, text in [
            (20240101, "2024-01-01"),
            (20240201, "2024-02-01"),
            (20240301, "2024-03-01"),
        ]:
            self.date(key, text)
        self.vendor(1, "Vendor")
        self.fact(1, 20240101, 1, 100)
        self.fact(2, 20240301, 1, 200)
        result = pd.read_sql_query(QUERIES["Q5"], self.connection)
        self.assertEqual(result.monthly_spend.tolist(), [100, 0, 200])
        self.assertEqual(result.running_total.tolist(), [100, 100, 300])
        self.assertTrue(pd.isna(result.month_over_month_pct_change.iloc[0]))
        self.assertEqual(result.month_over_month_pct_change.iloc[1], -100)
        self.assertTrue(pd.isna(result.month_over_month_pct_change.iloc[2]))

    def test_adjacent_raise_excludes_unchanged_snapshot(self):
        self.employee(1, "E1", 100, "2020-01-01", "2023-01-01", 0)
        self.employee(2, "E1", 150, "2023-01-01", "2024-01-01", 0)
        self.employee(3, "E1", 150, "2024-01-01", "9999-12-31", 1)
        result = pd.read_sql_query(QUERIES["Q6"], self.connection)
        self.assertEqual(result.change_date.tolist(), ["2023-01-01"])
        self.assertEqual(result.increase_amount.tolist(), [50])
        self.assertEqual(result.increase_pct.tolist(), [50])


class ArtifactTests(unittest.TestCase):
    def test_enriched_output_and_lookup_uniqueness(self):
        transactions = pd.read_csv(OUT / "transactions_clean.csv")
        self.assertEqual(len(transactions), 50000)
        self.assertFalse(transactions.transaction_id.duplicated().any())
        self.assertEqual(transactions.amount_aed.isna().sum(), 0)
        self.assertTrue(
            transactions.loc[transactions.amount.isna(), "amount_aed"].eq(0).all()
        )
        self.assertTrue(
            transactions.is_approved.eq(transactions.approved_by.notna()).all()
        )
        projects = pd.DataFrame(
            {
                "project_id": ["P1", "P1"],
                "project_name": ["One", "Two"],
                "department": ["A", "A"],
            }
        )
        employees = pd.DataFrame({"employee_id": ["E1"], "full_name": ["Person"]})
        sample = pd.DataFrame({"project_id": ["P1"], "approved_by": ["E1"]})
        with self.assertRaises(pd.errors.MergeError):
            enrich_transactions(sample, projects, employees)

    def test_generated_query_columns_and_real_sums(self):
        expected = {
            "Q1": [
                "department",
                "total_budget",
                "total_actual_cost",
                "spend_percentage",
                "over_budget",
            ],
            "Q2": [
                "full_name",
                "email",
                "active_project_count",
                "combined_budget_responsibility",
                "combined_actual_spend",
            ],
            "Q3": [
                "vendor_name",
                "total_spend",
                "transaction_count",
                "percentage_of_total_spend",
                "risk_flag",
            ],
            "Q4": [
                "project_id",
                "project_name",
                "department",
                "project_status",
                "open_transaction_count",
                "open_transaction_value",
            ],
            "Q5": [
                "year_month",
                "category",
                "monthly_spend",
                "running_total",
                "month_over_month_pct_change",
            ],
            "Q6": [
                "employee_id",
                "full_name",
                "change_date",
                "previous_salary",
                "new_salary",
                "increase_amount",
                "increase_pct",
            ],
        }
        for question, columns in expected.items():
            frame = pd.read_csv(OUT / (question.lower() + "_results.csv"))
            self.assertEqual(frame.columns.tolist(), columns)
        monthly = pd.read_csv(OUT / "q5_results.csv")
        transactions = pd.read_csv(OUT / "transactions_clean.csv")
        self.assertAlmostEqual(
            monthly.monthly_spend.sum(), transactions.amount.sum(), places=2
        )
        self.assertEqual((OUT / "dashboard_mockup.pdf").read_bytes()[:5], b"%PDF-")
        benchmark = json.loads((OUT / "benchmark_results.json").read_text())
        self.assertTrue(benchmark["results_equal"])
        self.assertTrue(
            any(
                "idx_transactions_status_amount_project" in row[-1]
                for row in benchmark["optimized_plan"]
            )
        )
        with closing(sqlite3.connect(OUT / "analytics.sqlite")) as connection:
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )


if __name__ == "__main__":
    unittest.main()
