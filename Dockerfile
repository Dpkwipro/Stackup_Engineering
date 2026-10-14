# Task 4.1: install only dependencies needed by the ETL.
FROM python:3.11-slim AS builder
WORKDIR /build
COPY solutions/submissions/deepak_shinghal/04_infrastructure/requirements.txt requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY datasets /app/datasets
COPY starter_files/etl_starter.py /app/starter_files/etl_starter.py
COPY solutions/submissions/deepak_shinghal /app/solutions/submissions/deepak_shinghal
ENV DATA_DIR=/app/datasets OUTPUT_DIR=/app/outputs PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "starter_files/etl_starter.py"]
