# Data quality: transactions

| Rule | Name | Dimension | Checked | Passed | Failed | Score | Status |
|---|---|---|---:|---:|---:|---:|---|
| R044 | transaction_id must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R045 | project_id must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R046 | vendor_id must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R047 | vendor_name must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R048 | category must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R049 | amount must be present | completeness | 50000 | 49260 | 740 | 98.52% | PASS |
| R050 | currency must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R051 | transaction_date must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R052 | approved_by must be present | completeness | 50000 | 47556 | 2444 | 95.11% | PASS |
| R053 | payment_status must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R054 | invoice_ref must be present | completeness | 50000 | 50000 | 0 | 100.0% | PASS |
| R055 | notes must be present | completeness | 50000 | 39249 | 10751 | 78.5% | FAIL |
| R056 | Key must be present and unique | uniqueness | 50000 | 50000 | 0 | 100.0% | PASS |
| R057 | amount within allowed range | numeric_validity | 49260 | 49260 | 0 | 100.0% | PASS |
| R058 | transaction_date must be a valid date | date_validity | 50000 | 50000 | 0 | 100.0% | PASS |
| R059 | amount cannot be negative | consistency | 49260 | 49260 | 0 | 100.0% | PASS |
| R060 | project_id must reference an existing record | referential_integrity | 50000 | 50000 | 0 | 100.0% | PASS |
| R061 | approved_by must reference an existing record | referential_integrity | 47556 | 47556 | 0 | 100.0% | PASS |
| R078 | Transactions updated within 30 days | freshness | 1 | 0 | 1 | 0.0% | FAIL |
| R079 | Check repeated transaction amounts | distribution | 1 | 1 | 0 | 100.0% | PASS |

## Details

- R044: Total rows: 50000; excluded rows: 0
- R045: Total rows: 50000; excluded rows: 0
- R046: Total rows: 50000; excluded rows: 0
- R047: Total rows: 50000; excluded rows: 0
- R048: Total rows: 50000; excluded rows: 0
- R049: Total rows: 50000; excluded rows: 0
- R050: Total rows: 50000; excluded rows: 0
- R051: Total rows: 50000; excluded rows: 0
- R052: Total rows: 50000; excluded rows: 0
- R053: Total rows: 50000; excluded rows: 0
- R054: Total rows: 50000; excluded rows: 0
- R055: Total rows: 50000; excluded rows: 0
- R056: Total rows: 50000; excluded rows: 0
- R057: Total rows: 50000; excluded rows: 740
- R058: Total rows: 50000; excluded rows: 0
- R059: Total rows: 50000; excluded rows: 740
- R060: Total rows: 50000; excluded rows: 0
- R061: Total rows: 50000; excluded rows: 2444
- R078: Latest date: 2026-08-04; age: 71 days; limit: 30 days; invalid dates: 0
- R079: Most common share: 0.02%; limit: 30%; non-null rows: 49260
