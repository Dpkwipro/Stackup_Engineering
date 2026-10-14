-- Benchmark queries run against employees/projects/transactions staging tables.
-- Employees contains only current cleaned employees, preventing SCD row duplication.
-- The runner rebuilds these tables without indexes before measuring the baseline.

-- ORIGINAL
-- Exact starter query. The scalar AVG subquery is UNCORRELATED: it references
-- no outer aliases. It is not necessarily executed once per transaction.
SELECT
    e.full_name,
    e.department,
    e.role,
    p.project_name,
    p.status,
    p.budget,
    p.actual_cost,
    t.amount,
    t.category,
    t.payment_status,
    t.transaction_date
FROM employees e, projects p, transactions t
WHERE e.employee_id = p.project_manager_id
AND   p.project_id  = t.project_id
AND   p.status NOT IN ('Completed', 'On Hold')
AND   t.payment_status = 'Pending'
AND   t.amount > (
        SELECT AVG(amount)
        FROM transactions
        WHERE payment_status = 'Pending'
      )
ORDER BY e.department, t.amount DESC;

-- INDEXES
-- Employee ID supports equality lookup after filtering project/transaction rows.
-- UNIQUE also documents that current employees have one row per source ID.
CREATE UNIQUE INDEX idx_employees_id ON employees(employee_id);
-- Project ID is first/only because the query probes a specific transaction's project.
CREATE UNIQUE INDEX idx_projects_id ON projects(project_id);
-- Equality on payment_status comes first, then the amount range, then the project
-- join key. Also covers amount for AVG over pending records. SQLite can seek into
-- Pending amounts rather than scan all 50,000 transactions. Extra indexed columns
-- increase storage and make inserts/amount/status updates more expensive.
CREATE INDEX idx_transactions_status_amount_project
    ON transactions(payment_status, amount, project_id);

-- OPTIMIZED
-- Three changes: explicit JOIN conditions, a named CTE for the pending average,
-- and early pending/amount filtering. Select only the needed output columns.
-- SQLite may inline CTEs; clearer SQL alone does not guarantee a different plan.
-- The AVG uses raw amounts (not zero-filled amount_aed) to preserve original semantics.
WITH pending_average AS (
    SELECT AVG(amount) AS average_amount FROM transactions WHERE payment_status = 'Pending'
), filtered_transactions AS (
    SELECT project_id, amount, category, payment_status, transaction_date
    FROM transactions
    WHERE payment_status = 'Pending'
      AND amount > (SELECT average_amount FROM pending_average)
), active_projects AS (
    SELECT project_id, project_manager_id, project_name, status, budget, actual_cost
    FROM projects WHERE status NOT IN ('Completed', 'On Hold')
)
SELECT e.full_name, e.department, e.role, p.project_name, p.status,
       p.budget, p.actual_cost, t.amount, t.category, t.payment_status, t.transaction_date
FROM filtered_transactions t
JOIN active_projects p ON p.project_id = t.project_id
JOIN employees e ON e.employee_id = p.project_manager_id
ORDER BY e.department, t.amount DESC;

-- MEASURED BENCHMARK (generated; see benchmark_results.json for all runs)
-- SQLite 3.53.2: EXPLAIN QUERY PLAN + wall-clock timing.
-- SQLite does not support EXPLAIN ANALYZE; no invented per-operator timings.
-- Seven warm runs; median includes complete result fetching; automatic_index ON.
-- Original: 14.196 ms; rewrite without indexes: 14.047 ms.
-- Optimized with indexes: 6.084 ms; speedup 2.33x.
-- Equivalent result multisets: True (923 rows).
-- ORIGINAL EXPLAIN QUERY PLAN:
-- (6, 0, 216, 'SCAN t')
-- (15, 0, 0, 'SCALAR SUBQUERY 1')
-- (20, 15, 216, 'SCAN transactions')
-- (55, 0, 53, 'SEARCH p USING AUTOMATIC PARTIAL COVERING INDEX (project_id=?)')
-- (78, 0, 53, 'SEARCH e USING AUTOMATIC COVERING INDEX (employee_id=?)')
-- (102, 0, 0, 'USE TEMP B-TREE FOR ORDER BY')
-- OPTIMIZED EXPLAIN QUERY PLAN:
-- (9, 0, 50, 'SEARCH transactions USING INDEX idx_transactions_status_amount_project (payment_status=? AND amount>?)')
-- (13, 0, 0, 'SCALAR SUBQUERY 2')
-- (16, 13, 0, 'CO-ROUTINE pending_average')
-- (19, 16, 54, 'SEARCH transactions USING COVERING INDEX idx_transactions_status_amount_project (payment_status=?)')
-- (32, 13, 16, 'SCAN pending_average')
-- (45, 0, 46, 'SEARCH projects USING INDEX idx_projects_id (project_id=?)')
-- (58, 0, 46, 'SEARCH e USING INDEX idx_employees_id (employee_id=?)')
-- (81, 0, 0, 'USE TEMP B-TREE FOR ORDER BY')
-- ANALYSIS: the baseline scans transactions for its main query and pending AVG.
-- Indexed version uses payment_status equality and amount range to reduce transaction reads.
-- Project/employee equality joins use ID indexes; ORDER BY still needs a temporary B-tree.
-- Plans do not expose operator costs, so no exact most-expensive operator is claimed.
-- No correlated subquery exists here: the scalar AVG has no reference to outer rows.
-- SELECT time includes sorting/fetching, which indexes cannot eliminate in this ordering.
-- A 10x gain is not guaranteed: data selectivity, automatic indexes and warm caches matter.
-- Original/rewrite timings and actual index names are recorded above; no synthetic slowdown.
