"""Tests for the 03 big data solution."""

from pathlib import Path
import json
import tempfile
import unittest
import pandas as pd
from airflow_tasks import run_data_quality_checks
from kafka_streaming import is_critical
from spark_pipeline import (
    get_spark_session,
    load_events,
    validate_events,
    escalation_log,
    daily_event_volume,
    OUT,
)


class QualityAndKafkaTests(unittest.TestCase):
    def test_completeness_threshold_and_duplicate_key(self):
        acceptable = pd.DataFrame({"id": ["1", "2", "3", "4", None]})
        self.assertEqual(
            run_data_quality_checks(acceptable, "fixture", ["id"])["completeness_pct"][
                "id"
            ],
            80,
        )
        with self.assertRaisesRegex(ValueError, "below 80%"):
            run_data_quality_checks(
                pd.DataFrame({"id": ["1", None, None]}), "fixture", ["id"]
            )
        with self.assertRaisesRegex(ValueError, "duplicate primary"):
            run_data_quality_checks(pd.DataFrame({"id": ["1", "1"]}), "fixture", ["id"])

    def test_critical_forwarding_predicate(self):
        self.assertTrue(
            is_critical(
                {"event_type": "escalation_raised", "payload": {"severity": "Critical"}}
            )
        )
        self.assertFalse(
            is_critical(
                {
                    "event_type": "escalation_resolved",
                    "payload": {"severity": "Critical"},
                }
            )
        )
        self.assertFalse(
            is_critical(
                {"event_type": "escalation_raised", "payload": {"severity": "High"}}
            )
        )
        self.assertFalse(
            is_critical({"event_type": "escalation_raised", "payload": None})
        )


class SparkEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = get_spark_session()

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_dedup_and_temporal_matching_without_reused_resolution(self):
        records = []

        def add(identifier, event_type, hour, user="U1"):
            records.append(
                {
                    "event_id": identifier,
                    "event_type": event_type,
                    "project_id": "P1",
                    "user_id": user,
                    "timestamp": f"2025-01-01T{hour:02d}:00:00Z",
                    "payload": {"severity": "Critical", "resolved_by": "U2"},
                }
            )

        add("r1", "escalation_raised", 10)
        add("r1", "escalation_raised", 11)
        add("s0", "escalation_resolved", 9)
        add("s1", "escalation_resolved", 11)
        add("r2", "escalation_raised", 12)
        add("r3", "escalation_raised", 13)
        add("s3", "escalation_resolved", 14)
        add("bad", "login", 15, user=None)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events_fixture.jsonl"
            json_lines = []
            for record in records:
                json_lines.append(json.dumps(record))
            path.write_text("\n".join(json_lines) + "\n")
            clean, counts = validate_events(load_events(self.spark, folder))
            try:
                self.assertEqual(counts["missing_ids_dropped"], 1)
                self.assertEqual(counts["duplicate_ids_dropped"], 1)
                rows = {}
                for row in escalation_log(clean).collect():
                    rows[row.event_id] = row
                self.assertEqual(rows["r1"].resolution_time_hours, 1)
                self.assertEqual(rows["r1"].resolution_event_id, "s1")
                self.assertFalse(rows["r2"].resolved)
                self.assertIsNone(rows["r2"].resolved_at)
                self.assertEqual(rows["r3"].resolution_event_id, "s3")
                self.assertEqual(
                    daily_event_volume(clean).agg({"event_count": "sum"}).first()[0], 6
                )
            finally:
                clean.unpersist()


class SparkArtifactTests(unittest.TestCase):
    def test_real_totals_partitions_and_running_counts(self):
        root = Path(__file__).resolve().parents[4]
        monthly_tables = []
        for path in sorted((root / "datasets/events_stream").glob("events_*.jsonl")):
            monthly_tables.append(pd.read_json(path, lines=True))
        events = pd.concat(monthly_tables)
        project = pd.read_parquet(OUT / "project_activity_summary")
        users = pd.read_parquet(OUT / "user_activity_summary")
        daily = pd.read_parquet(OUT / "daily_event_volume")
        escalation = pd.read_parquet(OUT / "escalation_log")
        peak = pd.read_parquet(OUT / "peak_usage_analysis")
        self.assertEqual(len(events), 99996)
        self.assertEqual(
            int(project.total_events.sum()), int(events.project_id.notna().sum())
        )
        self.assertEqual(
            int(users.login_count.sum()), int(events.event_type.eq("login").sum())
        )
        self.assertEqual(
            int(users.logout_count.sum()), int(events.event_type.eq("logout").sum())
        )
        self.assertEqual(
            int(users.actions_taken.sum()),
            int((~events.event_type.isin(["login", "logout"])).sum()),
        )
        self.assertEqual(int(daily.event_count.sum()), len(events))
        ordered = daily.sort_values(["event_type", "event_date"])
        self.assertEqual(
            ordered.cumulative_count.tolist(),
            ordered.groupby("event_type", observed=True).event_count.cumsum().tolist(),
        )
        self.assertEqual(
            len(escalation), int(events.event_type.eq("escalation_raised").sum())
        )
        matched = escalation[escalation.resolved]
        self.assertFalse(matched.resolution_event_id.duplicated().any())
        self.assertTrue(matched.resolution_time_hours.ge(0).all())
        self.assertTrue(
            escalation.loc[~escalation.resolved, "resolved_at"].isna().all()
        )
        self.assertEqual(len(peak), 20)
        self.assertTrue(peak.total_events.is_monotonic_decreasing)
        self.assertTrue(any((OUT / "daily_event_volume").glob("event_date=*")))
        self.assertTrue(any((OUT / "escalation_log").glob("severity=*")))


if __name__ == "__main__":
    unittest.main()
