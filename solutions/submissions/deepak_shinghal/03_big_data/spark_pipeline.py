"""Process monthly events into five Parquet summaries (Task 3.1)."""

from pathlib import Path
import json
import logging
import os
import time
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    TimestampType,
    MapType,
)

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/results/deepak_shinghal/03_big_data/spark"
LOG = logging.getLogger(__name__)


def get_spark_session():
    # Explicit loopback hostname avoids dependence on the machine's LAN hostname.
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("PresightEventsProcessing")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def load_events(spark, events_dir):
    schema = StructType(
        [
            StructField("event_id", StringType(), True),
            StructField("event_type", StringType(), True),
            StructField("project_id", StringType(), True),
            StructField("user_id", StringType(), True),
            StructField("timestamp", TimestampType(), True),
            StructField("payload", MapType(StringType(), StringType()), True),
        ]
    )

    wildcard = str(Path(events_dir) / "events_*.jsonl")
    return spark.read.schema(schema).option("mode", "FAILFAST").json(wildcard)


def validate_events(raw):
    before = raw.count()
    valid_ids = raw.filter(
        F.col("event_id").isNotNull() & F.col("user_id").isNotNull()
    ).cache()
    after_ids = valid_ids.count()
    LOG.info(
        "ID validation: %d -> %d; dropped %d", before, after_ids, before - after_ids
    )
    if (
        valid_ids.filter(F.col("timestamp").isNull() | F.col("event_type").isNull())
        .limit(1)
        .count()
    ):
        raise ValueError("Missing timestamp/event_type prevents meaningful aggregation")
    # dropDuplicates alone is not ordered. row_number selects the earliest timestamp.
    order = Window.partitionBy("event_id").orderBy(
        "timestamp", "event_type", "user_id", "project_id", F.to_json(F.col("payload"))
    )
    clean = valid_ids.withColumn("occurrence", F.row_number().over(order))
    clean = clean.filter(F.col("occurrence") == 1).drop("occurrence")
    clean = clean.withColumn("event_date", F.to_date("timestamp"))
    clean = clean.withColumn("event_hour", F.hour("timestamp"))
    clean = clean.withColumn(
        "event_month", F.date_format("timestamp", "yyyy-MM")
    ).cache()
    after_duplicates = clean.count()
    LOG.info(
        "Deduplication: %d -> %d; dropped %d",
        after_ids,
        after_duplicates,
        after_ids - after_duplicates,
    )
    valid_ids.unpersist()
    return clean, {
        "raw_count": before,
        "after_id_drop": after_ids,
        "clean_count": after_duplicates,
        "missing_ids_dropped": before - after_ids,
        "duplicate_ids_dropped": after_ids - after_duplicates,
    }


def count_type(event_type):
    return F.sum(F.when(F.col("event_type") == event_type, 1).otherwise(0))


def project_activity_summary(events):
    project_events = events.filter(F.col("project_id").isNotNull())
    summary = project_events.groupBy("project_id").agg(
        F.count("*").alias("total_events"),
        count_type("escalation_raised").alias("escalation_count"),
        count_type("task_completed").alias("task_completions"),
        count_type("document_uploaded").alias("document_uploads"),
        F.max("timestamp").alias("last_event_timestamp"),
        F.countDistinct("user_id").alias("unique_users"),
        F.countDistinct("event_type").alias("unique_event_types"),
    )
    return summary.orderBy(F.desc("total_events"), "project_id")


def user_activity_summary(events):
    # Actions exclude BOTH login and logout, following task instructions over starter hints.
    action = ~F.col("event_type").isin("login", "logout")
    summary = events.groupBy("user_id").agg(
        count_type("login").alias("login_count"),
        count_type("logout").alias("logout_count"),
        F.sum(F.when(action, 1).otherwise(0)).alias("actions_taken"),
        F.countDistinct("project_id").alias("projects_touched"),
        F.min("timestamp").alias("first_active"),
        F.max("timestamp").alias("last_active"),
        F.countDistinct("event_date").alias("active_days"),
    )
    return summary.orderBy("user_id")


def escalation_log(events):
    """Match each raise to the first resolution before the next raise in its project."""
    raises = events.filter(F.col("event_type") == "escalation_raised").select(
        F.col("event_id"),
        F.col("project_id"),
        F.col("user_id").alias("raised_by"),
        F.col("timestamp").alias("raised_at"),
        F.col("payload")["severity"].alias("severity"),
    )
    # lead reads the next raise date within each project's timeline.
    timeline = Window.partitionBy("project_id").orderBy("raised_at", "event_id")
    raises = raises.withColumn(
        "next_raise_at", F.lead("raised_at").over(timeline)
    ).alias("r")
    resolutions = (
        events.filter(F.col("event_type") == "escalation_resolved")
        .select(
            F.col("event_id").alias("resolution_event_id"),
            F.col("project_id").alias("resolution_project"),
            F.col("timestamp").alias("resolved_at"),
            F.col("payload")["resolved_by"].alias("resolved_by"),
        )
        .alias("s")
    )
    # LEFT join keeps unmatched raises. Resolution must fall within this raise's interval.
    condition = (
        (F.col("r.project_id") == F.col("s.resolution_project"))
        & (F.col("s.resolved_at") >= F.col("r.raised_at"))
        & (
            F.col("r.next_raise_at").isNull()
            | (F.col("s.resolved_at") < F.col("r.next_raise_at"))
        )
    )
    candidates = raises.join(resolutions, condition, "left")
    first_resolution = Window.partitionBy("r.event_id").orderBy(
        F.col("s.resolved_at").asc_nulls_last(), F.col("s.resolution_event_id")
    )
    matches = candidates.withColumn(
        "match_number", F.row_number().over(first_resolution)
    )
    matches = matches.filter(F.col("match_number") == 1)
    # Keep resolution_event_id too: it lets us prove no resolution was reused.
    return matches.select(
        "r.event_id",
        "r.project_id",
        "r.raised_by",
        "r.raised_at",
        "r.severity",
        F.col("s.resolution_event_id").isNotNull().alias("resolved"),
        "s.resolved_by",
        "s.resolved_at",
        (
            (F.col("s.resolved_at").cast("long") - F.col("r.raised_at").cast("long"))
            / 3600.0
        ).alias("resolution_time_hours"),
        "s.resolution_event_id",
    )


def daily_event_volume(events):
    daily = events.groupBy("event_date", "event_type").agg(
        F.count("*").alias("event_count")
    )
    # Running SUM resets per event type; it accumulates from the first day to this day.
    days = (
        Window.partitionBy("event_type")
        .orderBy("event_date")
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )
    daily = daily.withColumn("cumulative_count", F.sum("event_count").over(days))
    return daily.orderBy("event_date", F.desc("event_count"))


def peak_usage_analysis(events):
    hourly = events.groupBy("event_date", "event_hour").agg(
        F.count("*").alias("total_events"),
        F.countDistinct("user_id").alias("unique_users"),
        F.countDistinct("event_type").alias("event_types_per_hour"),
    )
    busiest_first = hourly.orderBy(F.desc("total_events"), "event_date", "event_hour")
    return busiest_first.limit(20)


def write_parquet(table, name):
    path = OUT / name
    writer = table.coalesce(1).write.mode("overwrite")
    if name == "daily_event_volume":
        writer = writer.partitionBy("event_date")
    if name == "escalation_log":
        writer = writer.partitionBy("severity")
    writer.parquet(str(path))

    row_count = table.count()
    LOG.info("%s: wrote %d rows to %s", name, row_count, path)
    return row_count


def run_pipeline():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    spark = get_spark_session()
    try:
        raw = load_events(spark, ROOT / "datasets/events_stream").cache()
        LOG.info("Loaded %d events", raw.count())
        clean, metrics = validate_events(raw)
        raw.unpersist()
        builders = {
            "project_activity_summary": project_activity_summary,
            "user_activity_summary": user_activity_summary,
            "escalation_log": escalation_log,
            "daily_event_volume": daily_event_volume,
            "peak_usage_analysis": peak_usage_analysis,
        }
        metrics["tables"] = {}
        for name, build_table in builders.items():
            table_start = time.time()
            table = build_table(clean).cache()
            count = write_parquet(table, name)
            metrics["tables"][name] = {
                "row_count": count,
                "execution_seconds": time.time() - table_start,
            }
            if name == "escalation_log":
                matched = table.filter("resolved").count()
                reused = (
                    table.filter("resolved")
                    .groupBy("resolution_event_id")
                    .count()
                    .filter("count > 1")
                    .count()
                )
                if reused:
                    raise ValueError("Escalation matching reused a resolution")
                metrics["resolved_escalations"] = matched
                metrics["unresolved_escalations"] = count - matched
                resolution_count = clean.filter(
                    F.col("event_type") == "escalation_resolved"
                ).count()
                metrics["unmatched_resolution_events"] = resolution_count - matched
            table.unpersist()
        clean.unpersist()
        metrics["execution_seconds"] = time.time() - start
        metrics["events_per_second"] = (
            metrics["raw_count"] / metrics["execution_seconds"]
        )
        (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        LOG.info("Spark metrics: %s", metrics)
    finally:
        spark.stop()


if __name__ == "__main__":
    run_pipeline()
