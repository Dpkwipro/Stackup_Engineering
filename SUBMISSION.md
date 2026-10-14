# Engineering assessment submission

Use Python 3.11. Java 17 is needed for Spark; Docker Desktop runs Kafka and Airflow.

## Solutions and deliverables

The presentation, governance document and verified generated outputs are included in `outputs/` so reviewers can inspect the results without rerunning the pipelines. The scripts and services can regenerate them. Airflow includes a completed run; temporary staging files and duplicate runs are archived locally.

| Pillar | Implementation | Main evidence |
|---|---|---|
| 1 — Foundations | `solutions/submissions/deepak_shinghal/01_foundations/etl_pipeline.py`, `data_model.sql` | Cleaned data, employee versions and validated SQLite warehouse in `outputs/results/deepak_shinghal/01_foundations/` |
| 2 — SQL and visualisation | `02_sql_and_viz/queries.sql`, `query_optimization.sql`, `etl_full.py`, `dashboard.py` | Six query CSVs, benchmark evidence and `dashboard_mockup.pdf` in `outputs/results/deepak_shinghal/02_sql_and_viz/` |
| 3 — Big Data | `03_big_data/spark_pipeline.py`, `kafka_streaming.py`, `airflow_dag.py`, `airflow_tasks.py` | Five Parquet tables in `outputs/results/deepak_shinghal/03_big_data/spark/`, Kafka summary in `outputs/results/deepak_shinghal/03_big_data/kafka/`, completed Airflow run and quality-gate verification in `outputs/results/deepak_shinghal/03_big_data/airflow/` |
| 4 — Infrastructure and governance | Root Dockerfile/Compose override; `04_infrastructure/rule_config.csv`, `data_quality.py`; `starter_files/etl_starter.py` | `outputs/results/deepak_shinghal/04_infrastructure/data_governance_document.md`, four DQ score CSVs/markdown reports and `dq_results.json` in `outputs/results/deepak_shinghal/04_infrastructure/` |

Folders abbreviated above are under `solutions/submissions/deepak_shinghal/`.

The six-slide presentation is `outputs/engineering_assessment_four_pillars.pptx`; its PDF is `outputs/engineering_assessment_four_pillars.pdf`. The dashboard preview and Airflow screenshot are embedded in the presentation. The governance link points to the document in the Pillar 4 output folder. The separate dashboard PDF can be regenerated with the Pillar 2 script. The Airflow screenshot records successful demonstration runs under the earlier name; the submitted DAG uses `presight_etl_pipeline` as required.

## Run

From the repository root:

```bash
python solutions/submissions/deepak_shinghal/01_foundations/etl_pipeline.py
python solutions/submissions/deepak_shinghal/02_sql_and_viz/etl_full.py
python starter_files/etl_starter.py
python solutions/submissions/deepak_shinghal/04_infrastructure/data_quality.py
```

Spark:

```bash
python solutions/submissions/deepak_shinghal/03_big_data/spark_pipeline.py
```

For Kafka, start the root Compose broker on port 9092, then run `03_big_data/kafka_streaming.py`. The separate Task 3 Compose broker exposes port 9094; change `KAFKA_SERVER` if using that broker. The required 50 ms producer delay means a full run takes several minutes.

Airflow:

```bash
cd solutions/submissions/deepak_shinghal/03_big_data
./start_airflow.sh
```

Open `http://localhost:8082`, use the displayed credentials, unpause `presight_etl_pipeline` and trigger a run. The script prints a 30-second countdown and then checks readiness; startup can take longer. `./stop_airflow.sh` stops Airflow and clears its saved webserver PID file.

Docker ETL:

```bash
docker build -t presight-etl .
docker run --rm -v "$(pwd)/outputs:/app/outputs" presight-etl
```

## Validation and limits

- Final validation passed 17 SQL/DQ tests and four Big Data tests, including Spark edge cases.
- Airflow verification confirms schedule/dependencies/retries and that a deliberately failed quality gate blocks downstream work.
- Q3 correctly returns zero vendors: none exceeds 5% of source transaction spend.
- SQL benchmarks report measured results; the suggested 10x speedup is not guaranteed. See the latest `benchmark_results.json`.
- Historical input dates can fail freshness rules. DQ warnings are findings, not runner errors; governance policies are proposals rather than implemented production access controls.
- Employee salary bands, same-day history handling and the 2025-07-01 export boundary are documented assessment assumptions.

Run tests with `python -m pytest solutions/submissions/deepak_shinghal/02_sql_and_viz solutions/submissions/deepak_shinghal/04_infrastructure -q`. Big Data tests require Spark/Java and kafka-python. Read-only input files are preserved.

Virtual environments, caches and macOS metadata are excluded by `.gitignore`. Solutions and deliverables are included. No repository changes have been committed or pushed by this cleanup.
