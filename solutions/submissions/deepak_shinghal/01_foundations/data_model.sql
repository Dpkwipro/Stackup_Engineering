-- SQLite warehouse. Grain: one source transaction; amounts retain source currency.
-- Financial fields declare DECIMAL(18,2). SQLite applies NUMERIC affinity;
-- it does not enforce decimal precision/scale or exact decimal arithmetic.
-- Use a database with native DECIMAL support for exact financial calculations.
PRAGMA foreign_keys = ON;
-- Integer calendar key (YYYYMMDD), with ISO week and Monday=1 weekday.
CREATE TABLE dim_date (
 date_key INTEGER PRIMARY KEY, full_date TEXT NOT NULL UNIQUE,
 year INTEGER NOT NULL, quarter INTEGER NOT NULL, month INTEGER NOT NULL,
 month_name TEXT NOT NULL, week INTEGER NOT NULL, day INTEGER NOT NULL,
 day_of_week INTEGER NOT NULL, is_weekend INTEGER NOT NULL CHECK(is_weekend IN (0,1))
);
-- Projects are Type 1; source ID remains unique for reproducible lookup.
CREATE TABLE dim_project (
 project_key INTEGER PRIMARY KEY, project_id TEXT NOT NULL UNIQUE,
 project_name TEXT, department TEXT, status TEXT, start_date TEXT, end_date TEXT,
 budget DECIMAL(18,2) NOT NULL, actual_cost DECIMAL(18,2) NOT NULL, project_manager_id TEXT,
 priority TEXT, region TEXT
);
-- SCD2 uses half-open intervals [valid_from, valid_to). Salary/role/level
-- come from history new_* fields; attributes without history use the snapshot.
-- An unknown member supports unapproved transactions without losing facts.
CREATE TABLE dim_employee (
 employee_key INTEGER PRIMARY KEY, employee_id TEXT NOT NULL, full_name TEXT,
 email TEXT, department TEXT, role TEXT, level TEXT, hire_date TEXT,
 salary DECIMAL(18,2), manager_id TEXT, region TEXT, status TEXT, years_experience REAL,
 valid_from TEXT NOT NULL, valid_to TEXT NOT NULL,
 is_current INTEGER NOT NULL CHECK(is_current IN (0,1)), change_reason TEXT,
 CHECK(valid_from < valid_to),
 CHECK((is_current=1 AND valid_to='9999-12-31') OR
       (is_current=0 AND valid_to<'9999-12-31')),
 UNIQUE(employee_id, valid_from)
);
CREATE UNIQUE INDEX one_current_employee ON dim_employee(employee_id) WHERE is_current=1;
-- Vendor ID, rather than name, identifies a supplier; names may be shared.
CREATE TABLE dim_vendor (
 vendor_key INTEGER PRIMARY KEY, vendor_id TEXT NOT NULL UNIQUE, vendor_name TEXT
);
-- Only observed manager/approver relationships are loaded; no team membership
-- is invented. Links refer to employee versions, allowing time-aware analysis.
CREATE TABLE bridge_employee_project (
 employee_key INTEGER NOT NULL REFERENCES dim_employee(employee_key),
 project_key INTEGER NOT NULL REFERENCES dim_project(project_key),
 relationship TEXT NOT NULL CHECK(relationship IN ('Manager','Approver')),
 PRIMARY KEY(employee_key,project_key,relationship)
);
-- One row per transaction; employee is the approver version effective on its date.
CREATE TABLE fact_transactions (
 transaction_key INTEGER PRIMARY KEY, transaction_id TEXT NOT NULL UNIQUE,
 project_key INTEGER NOT NULL REFERENCES dim_project(project_key),
 employee_key INTEGER NOT NULL REFERENCES dim_employee(employee_key),
 vendor_key INTEGER NOT NULL REFERENCES dim_vendor(vendor_key),
 date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
 amount DECIMAL(18,2), currency TEXT, category TEXT, payment_status TEXT, invoice_ref TEXT
);
-- Q1: zero rows; partial unique index also enforces at most one current version.
SELECT employee_id, COUNT(*) AS current_count FROM dim_employee
WHERE is_current=1 GROUP BY employee_id HAVING COUNT(*) > 1;
-- Q2: employees with 2-5 versions.
SELECT employee_id, COUNT(*) AS version_count FROM dim_employee
GROUP BY employee_id ORDER BY version_count DESC, employee_id LIMIT 10;
-- Q3: strict inequalities permit adjacent half-open intervals; zero rows.
SELECT a.employee_id, a.employee_key, b.employee_key
FROM dim_employee a JOIN dim_employee b
 ON a.employee_id=b.employee_id AND a.employee_key<b.employee_key
 AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to;
-- Exactly one current version, including detection of zero current versions.
SELECT employee_id FROM dim_employee GROUP BY employee_id
HAVING SUM(is_current) <> 1;
