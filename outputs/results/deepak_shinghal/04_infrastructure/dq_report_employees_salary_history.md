# Data quality: employees_salary_history

| Rule | Name | Dimension | Checked | Passed | Failed | Score | Status |
|---|---|---|---:|---:|---:|---:|---|
| R062 | employee_id must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R063 | previous_salary must be present | completeness | 1826 | 1232 | 594 | 67.47% | FAIL |
| R064 | new_salary must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R065 | previous_role must be present | completeness | 1826 | 1232 | 594 | 67.47% | FAIL |
| R066 | new_role must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R067 | previous_level must be present | completeness | 1826 | 1232 | 594 | 67.47% | FAIL |
| R068 | new_level must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R069 | effective_date must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R070 | change_type must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R071 | change_reason must be present | completeness | 1826 | 1826 | 0 | 100.0% | PASS |
| R072 | Key must be present and unique | uniqueness | 1826 | 1826 | 0 | 100.0% | PASS |
| R073 | previous_salary within allowed range | numeric_validity | 1232 | 1232 | 0 | 100.0% | PASS |
| R074 | new_salary within allowed range | numeric_validity | 1826 | 1826 | 0 | 100.0% | PASS |
| R075 | effective_date must be a valid date | date_validity | 1826 | 1826 | 0 | 100.0% | PASS |
| R076 | new_salary cannot be negative | consistency | 1826 | 1826 | 0 | 100.0% | PASS |
| R077 | employee_id must reference an existing record | referential_integrity | 1826 | 1826 | 0 | 100.0% | PASS |

## Details

- R062: Total rows: 1826; excluded rows: 0
- R063: Total rows: 1826; excluded rows: 0
- R064: Total rows: 1826; excluded rows: 0
- R065: Total rows: 1826; excluded rows: 0
- R066: Total rows: 1826; excluded rows: 0
- R067: Total rows: 1826; excluded rows: 0
- R068: Total rows: 1826; excluded rows: 0
- R069: Total rows: 1826; excluded rows: 0
- R070: Total rows: 1826; excluded rows: 0
- R071: Total rows: 1826; excluded rows: 0
- R072: Total rows: 1826; excluded rows: 0
- R073: Total rows: 1826; excluded rows: 594
- R074: Total rows: 1826; excluded rows: 0
- R075: Total rows: 1826; excluded rows: 0
- R076: Total rows: 1826; excluded rows: 0
- R077: Total rows: 1826; excluded rows: 0
