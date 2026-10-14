# Pillar 2 — SQL and Visualization

All four tasks are implemented. Source code stays in the submission folder;
outputs follow the repository-wide convention under
`outputs/results/deepak_shinghal/02_sql_and_viz/`. Starter files are unchanged.

## Run

Requires Python 3.9+, pandas, matplotlib and SQLite 3.25+ (SQLite ships with Python).
No Docker, Power BI or extra database server is needed for these tasks.

```sh
python3 solutions/submissions/deepak_shinghal/02_sql_and_viz/etl_full.py
python3 -m unittest discover -s solutions/submissions/deepak_shinghal/02_sql_and_viz -p 'test_*.py' -v
```

The runner uses the Foundations cleaned data and populated SCD2 warehouse. It
runs Foundations first if required artifacts are missing. If source inputs have
changed since Foundations was built, rerun Foundations first; source/fact and
current employee/project consistency checks reject a stale warehouse.

## Deliverables

| Task | Implementation | Generated output |
|---|---|---|
| 2.1 | `queries.sql`, six commented SQLite queries | `q1_results.csv` through `q6_results.csv` |
| 2.2 | `etl_full.py`, basic steps and explanatory comments | Three cleaned CSVs, `pipeline_summary.txt`, `analytics.sqlite` |
| 2.3 | `query_optimization.sql`, original/rewrite/index DDL and measured plans | `benchmark_results.json` |
| 2.4 | `dashboard.py`, annotated one-page dashboard | `dashboard_mockup.pdf`, `dashboard_preview.png`, chart data CSVs |

Read `run_pipeline()` first to follow extraction, enrichment, warehouse loading,
SQL, benchmarking, dashboard generation and CSV export. See the root `SUBMISSION.md` for the task mapping, execution commands and validation results.

## Decisions and verified results

- 500 projects, 1,000 employees and all 50,000 transactions retained.
- Source `amount` stays null for 740 unknown amounts. Reporting `amount_aed`
  substitutes 0.0, as Task 2.2 requests; SUM/AVG in warehouse queries ignore nulls.
- 2,444 absent approver IDs stay null; their current display name is
  `Unknown approver` and `is_approved` is False. A present approver ID makes that
  flag True, independently of payment status and the historical temporal match.
- Current cleaned employees supply enrichment names. Q2 joins current SCD2 rows;
  Q6 compares adjacent historical versions with the required self-join.
- All source transactions are AED. Other currencies would require conversion;
  this pipeline rejects them instead of labelling unconverted amounts AED.
- Joins are LEFT and explicitly many-to-one; unknown project references fail.
- Business aggregates run in SQL without fetching a full joined transaction table.
  The enrichment table is materialised because its CSV is a required deliverable.
- Q1 returns Legal at approximately 90.45% of budget; Q2 returns no managers above
  three active projects; Q3 returns no vendors above 5%; Q4 returns 435 projects;
  Q5 returns 784 category/month rows; Q6 returns the 20 largest positive increases.
  Empty Q2/Q3 outputs are correct findings, not missing implementations.
- Q5 covers the entire actual transaction range, with zero-activity calendar
  months included. The first month or a zero previous-month denominator gives a
  null month-over-month percentage, rather than infinity.
- Eight tests verify strict thresholds, current-only manager joins, vendor identity,
  zero denominators, month gaps, adjacent raises, output columns and actual totals.

## Optimization evidence

The original starter SQL is preserved. The rewrite uses explicit JOINs, an average
CTE and early transaction/project filtering. Three indexes support employee ID,
project ID and `(payment_status, amount, project_id)` transaction lookup. Each
index has a rationale and write/storage trade-off in the SQL file.

The runner measures seven warm fully fetched runs and reports medians. It measures
the rewrite before adding indexes as well, so indexing benefits are distinguishable
from syntax changes. Original and optimized results are compared as multisets,
including duplicate rows, to prove equivalent contents (923 rows).

Actual `EXPLAIN QUERY PLAN` output and before/after timings are pasted as SQL
comments by the runner. SQLite does not support PostgreSQL's `EXPLAIN ANALYZE`,
so supported plans and separately measured execution times are supplied instead.
The original AVG subquery is **uncorrelated**; the task's assumption that it is
executed for every row is not applicable here. The optimized plan uses the named
transaction index for status/amount and the project/employee lookup indexes.
Both plans retain a temporary B-tree for the output ordering.

The first measured run achieved **2.33x** (8.515 ms to 3.660 ms), not 10x.
The task's suggested 10x is not guaranteed on this dataset/SQLite engine. We report
real measurements without disabling baseline optimizations or inventing delays.
The latest run's results are authoritative in `benchmark_results.json` and the SQL
comments; runtime varies with machine load, caching and SQLite version.

The first full pipeline run completed in **22.341 seconds**, including dashboard
font-cache initialization, benchmarking and CSV exports. The latest runtime is in
`pipeline_summary.txt`; missing Foundations regeneration may add extra runtime.

## Dashboard interpretation

The PDF is the explicitly permitted mockup submission, not a `.pbix` file. It has
all required visuals, the trainee name/date, actual dataset values and annotations
explaining chart choices. All categories appear on the monthly line chart.

The department chart uses Q1 aggregation before its >90% risk filter so all
budget/spend comparisons are visible. The donut uses Q3 aggregation before its
>5% risk filter so all spend is included; it shows top five vendor IDs/names plus
Other. Using threshold-filtered Q3 would show an empty chart on this dataset.

Slicers are visibly specified static design controls. Region/status filter
related projects and facts; year filters transaction visuals/counts. Budget and
actual project-cost snapshot totals are not falsely allocated to transaction years.
Project actual cost and transaction spend are distinct measures from the sources.
SQLite's DECIMAL declarations do not enforce exact financial arithmetic.
