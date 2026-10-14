# Data quality: employees

| Rule | Name | Dimension | Checked | Passed | Failed | Score | Status |
|---|---|---|---:|---:|---:|---:|---|
| R020 | employee_id must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R021 | full_name must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R022 | email must be present | completeness | 1000 | 990 | 10 | 99.0% | PASS |
| R023 | department must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R024 | role must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R025 | level must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R026 | hire_date must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R027 | salary must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R028 | manager_id must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R029 | region must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R030 | status must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R031 | years_experience must be present | completeness | 1000 | 1000 | 0 | 100.0% | PASS |
| R032 | Key must be present and unique | uniqueness | 1000 | 1000 | 0 | 100.0% | PASS |
| R033 | salary within allowed range | numeric_validity | 1000 | 1000 | 0 | 100.0% | PASS |
| R034 | years_experience within allowed range | numeric_validity | 1000 | 995 | 5 | 99.5% | FAIL |
| R035 | hire_date must be a valid date | date_validity | 1000 | 992 | 8 | 99.2% | FAIL |
| R036 | Junior salary band | consistency | 187 | 184 | 3 | 98.4% | FAIL |
| R037 | Mid salary band | consistency | 366 | 366 | 0 | 100.0% | PASS |
| R038 | Senior salary band | consistency | 303 | 303 | 0 | 100.0% | PASS |
| R039 | Lead salary band | consistency | 114 | 114 | 0 | 100.0% | PASS |
| R040 | Director salary band | consistency | 30 | 30 | 0 | 100.0% | PASS |
| R041 | Senior role matches level | consistency | 69 | 22 | 47 | 31.88% | FAIL |
| R042 | Lead role matches level | consistency | 54 | 4 | 50 | 7.41% | FAIL |
| R043 | manager_id must reference an existing record | referential_integrity | 1000 | 995 | 5 | 99.5% | FAIL |

## Details

- R020: Total rows: 1000; excluded rows: 0
- R021: Total rows: 1000; excluded rows: 0
- R022: Total rows: 1000; excluded rows: 0
- R023: Total rows: 1000; excluded rows: 0
- R024: Total rows: 1000; excluded rows: 0
- R025: Total rows: 1000; excluded rows: 0
- R026: Total rows: 1000; excluded rows: 0
- R027: Total rows: 1000; excluded rows: 0
- R028: Total rows: 1000; excluded rows: 0
- R029: Total rows: 1000; excluded rows: 0
- R030: Total rows: 1000; excluded rows: 0
- R031: Total rows: 1000; excluded rows: 0
- R032: Total rows: 1000; excluded rows: 0
- R033: Total rows: 1000; excluded rows: 0
- R034: Total rows: 1000; excluded rows: 0
- R035: Total rows: 1000; excluded rows: 0
- R036: Total rows: 1000; excluded rows: 813
- R037: Total rows: 1000; excluded rows: 634
- R038: Total rows: 1000; excluded rows: 697
- R039: Total rows: 1000; excluded rows: 886
- R040: Total rows: 1000; excluded rows: 970
- R041: Total rows: 1000; excluded rows: 931
- R042: Total rows: 1000; excluded rows: 946
- R043: Total rows: 1000; excluded rows: 0
