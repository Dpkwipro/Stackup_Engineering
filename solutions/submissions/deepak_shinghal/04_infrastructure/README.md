# Pillar 4 — Infrastructure and governance

## Files by task

| Task | Files |
|---|---|
| 4.1 Docker | Root `Dockerfile`, `.dockerignore`, `docker-compose.override.yml`; this folder's `requirements.txt`; `starter_files/etl_starter.py` |
| 4.2 Governance | `outputs/results/deepak_shinghal/04_infrastructure/data_governance_document.md` |
| 4.3 Quality | `rule_config.csv`, `data_quality.py`, `test_data_quality.py`; `run_data_quality_checks()` imported and called by `starter_files/etl_starter.py` |

The entry point performs the Task 2.2 CSV cleaning/enrichment using the existing implementations. It handles 500 projects, 1,000 employees and 50,000 transactions, and checks all four raw datasets including 1,826 salary-history events. It does not execute unrelated SQL benchmarks or generate the PDF dashboard.

## Run locally

```bash
python starter_files/etl_starter.py
```

`DATA_DIR` defaults to repository `datasets/`; `OUTPUT_DIR` defaults to repository `outputs/`. Change them with environment variables:

```bash
DATA_DIR=/path/to/input OUTPUT_DIR=/path/to/results python starter_files/etl_starter.py
```

## Run in Docker

From the repository root:

```bash
docker build -t presight-etl .
time docker run --rm -v "$(pwd)/outputs:/app/outputs" presight-etl
```

The multi-stage image uses `python:3.11-slim` and installs from this folder's pinned `requirements.txt`, copied as `/build/requirements.txt` and `/app/requirements.txt`. This ETL needs Pandas and NumPy; the root requirements list includes optional/separate Kafka, Airflow and other tooling and remains unchanged. The runtime contains neither the wheel cache nor build tooling.

Use custom container paths with read-only inputs:

```bash
docker run --rm \
  -e DATA_DIR=/input -e OUTPUT_DIR=/results \
  -v "$(pwd)/datasets:/input:ro" \
  -v "$(pwd)/outputs:/results" presight-etl
```

Bonus Compose command (root compose automatically loads the override):

```bash
docker compose run --rm etl
```

No Kafka or Airflow service is required to run this ETL.

## Task 4.3 — CSV rules and scored output

The implementation uses `rule_config.csv` and `data_quality.py`. There is no second Python config to maintain. Run just the quality checks from any directory:

```bash
python solutions/submissions/deepak_shinghal/04_infrastructure/data_quality.py
```

From this folder, use `python data_quality.py`. DATA_DIR and OUTPUT_DIR override input/output folders. DQ_CONFIG_FILE selects a different CSV for the standalone runner.

The config has exactly six columns:

```csv
rule_id,rule_name,tablename,column,dimension,condition
R001,Salary must be present,employees,salary,completeness,not_null; score >= 95%
R002,Employee ID must be unique,employees,employee_id,uniqueness,unique
R003,Salary within range,employees,salary,numeric_validity,between 10000 and 100000
R004,Hire date not in future,employees,hire_date,date_validity,not_future
R005,Project dates in order,projects,start_date,consistency,before end_date
R006,Manager must exist,projects,project_manager_id,referential_integrity,exists in employees.employee_id
R007,Transactions updated within 30 days,transactions,transaction_date,freshness,max_date within 30 days
R008,Check repeated amounts,transactions,amount,distribution,most_common_share <= 30%
```

The shipped CSV has 79 rules covering all four datasets and all six required dimensions, plus freshness and distribution. Completeness is measured for every source column. Rule IDs must be unique. Add a row to add a check; Python does not need to change for a supported condition. Unsupported conditions and malformed config raise a clear error; condition text is never executed as Python or SQL.

| Dimension | Supported condition |
|---|---|
| completeness | `not_null` |
| uniqueness | `unique`; use `id1\|id2` in column for composite keys |
| numeric_validity | `between 10000 and 100000` (inclusive bounds) |
| date_validity | `valid_date` or `not_future` |
| consistency | `before end_date`, `non_negative`, `between 12000 and 17000 when level = Junior`, `equals Senior when role starts_with Senior` |
| referential_integrity | `exists in employees.employee_id` |
| freshness | `max_date within 30 days` |
| distribution | `most_common_share <= 30%` |

Append `; score >= 95%` to set a minimum passing score. Without it, the required score is 100%. Comparison uses the unrounded score; display rounds to two decimals. Append `; allow_null` to skip missing optional values for numeric/date/consistency/reference checks. Completeness always checks all rows. Blank or whitespace-only values count as missing.

Score = passed rows / checked rows × 100. Reports explicitly show excluded rows in details. Conditional rules check only matching employees; no applicable rows get NOT APPLICABLE and a blank score. For uniqueness, every occurrence of a repeated key fails, including the first. A missing configured column/reference is FAIL with no measurable score, not a false 100%. Empty sources fail completeness and uniqueness.

Freshness and distribution are one dataset-level evaluation each, scoring 100% or 0%. Freshness shows the latest date, its age and the configured age limit. Future latest dates or malformed non-null dates also fail. An all-missing date column fails freshness because no recent date can be established. Distribution uses non-null values and fails only when the most-common share is strictly above the limit; all-missing values are NOT APPLICABLE. Repetition can be legitimate, so this flag requires owner review.

Dates use `%Y-%m-%d`; freshness/non-future checks use today's date in Asia/Dubai. These are historical assessment extracts, so the 30-day freshness rule is expected to fail today. This is a real finding, not an execution error. The config keeps the requested 30-day limit.

Salary bands and Senior/Lead title expectations are assessment assumptions requiring HR confirmation. History uniqueness uses an event signature because there is no source event ID and distinct same-day changes are allowed. Missing previous values on initial history events remain visible in completeness scores. Rules do not alter source data or force it to pass.

DQ outputs are grouped under `OUTPUT_DIR/results/deepak_shinghal/04_infrastructure/` (by default `outputs/results/deepak_shinghal/04_infrastructure/`):

- `dq_scores_<tablename>.csv`: one row per rule, counts, score, threshold, status and details.
- `dq_report_<tablename>.md`: readable score table and details.
- `dq_results.json`: results for all configured datasets, including checks_run/passed/failed/not_applicable.

The ETL entry point imports the same runner and saves DQ reports in the same Pillar 4 folder. It adds cleaned CSVs, `quality_summary.json` and `pipeline_summary.txt`. Every failed rule logs a WARNING. Reporting failures do not stop the ETL; owners review the findings. Existing Task 2.2 input validations still reject critical invalid data.

## Verification

```bash
python -m pytest solutions/submissions/deepak_shinghal/04_infrastructure -q
```

Nine framework tests cover the six required dimensions, exact threshold boundaries, blank/null handling, duplicate combinations, missing references/columns, salary/title conditions, empty sources, freshness and distribution boundaries, CSV rule addition without code changes, config validation and report exports.

The assignment names reports directly under `outputs/`; this submission groups them in the Pillar 4 subfolder as requested. `OUTPUT_DIR` remains the base output folder for both local and Docker runs.
