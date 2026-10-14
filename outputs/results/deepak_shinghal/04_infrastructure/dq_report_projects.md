# Data quality: projects

| Rule | Name | Dimension | Checked | Passed | Failed | Score | Status |
|---|---|---|---:|---:|---:|---:|---|
| R001 | project_id must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R002 | project_name must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R003 | department must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R004 | status must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R005 | start_date must be present | completeness | 500 | 435 | 65 | 87.0% | FAIL |
| R006 | end_date must be present | completeness | 500 | 214 | 286 | 42.8% | FAIL |
| R007 | budget must be present | completeness | 500 | 468 | 32 | 93.6% | PASS |
| R008 | actual_cost must be present | completeness | 500 | 440 | 60 | 88.0% | FAIL |
| R009 | project_manager_id must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R010 | priority must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R011 | region must be present | completeness | 500 | 500 | 0 | 100.0% | PASS |
| R012 | Key must be present and unique | uniqueness | 500 | 500 | 0 | 100.0% | PASS |
| R013 | budget within allowed range | numeric_validity | 468 | 468 | 0 | 100.0% | PASS |
| R014 | actual_cost within allowed range | numeric_validity | 440 | 440 | 0 | 100.0% | PASS |
| R015 | start_date must be a valid date | date_validity | 435 | 435 | 0 | 100.0% | PASS |
| R016 | end_date must be a valid date | date_validity | 214 | 214 | 0 | 100.0% | PASS |
| R017 | Project dates in order | consistency | 214 | 214 | 0 | 100.0% | PASS |
| R018 | actual_cost cannot be negative | consistency | 440 | 440 | 0 | 100.0% | PASS |
| R019 | project_manager_id must reference an existing record | referential_integrity | 500 | 500 | 0 | 100.0% | PASS |

## Details

- R001: Total rows: 500; excluded rows: 0
- R002: Total rows: 500; excluded rows: 0
- R003: Total rows: 500; excluded rows: 0
- R004: Total rows: 500; excluded rows: 0
- R005: Total rows: 500; excluded rows: 0
- R006: Total rows: 500; excluded rows: 0
- R007: Total rows: 500; excluded rows: 0
- R008: Total rows: 500; excluded rows: 0
- R009: Total rows: 500; excluded rows: 0
- R010: Total rows: 500; excluded rows: 0
- R011: Total rows: 500; excluded rows: 0
- R012: Total rows: 500; excluded rows: 0
- R013: Total rows: 500; excluded rows: 32
- R014: Total rows: 500; excluded rows: 60
- R015: Total rows: 500; excluded rows: 65
- R016: Total rows: 500; excluded rows: 286
- R017: Total rows: 500; excluded rows: 286
- R018: Total rows: 500; excluded rows: 60
- R019: Total rows: 500; excluded rows: 0
