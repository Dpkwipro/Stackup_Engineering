-- SQLite queries against analytics.sqlite, copied from the Foundations warehouse.
-- Each question is delimited by a Q marker so the Python runner can export it.
-- SUM ignores null amounts; unknown money is not silently claimed as confirmed zero.
-- 100.0 forces fractional division; NULLIF prevents division by zero.

-- Q1
-- Aggregate projects first. Joining transaction rows here would repeat each budget.
-- HAVING filters aggregated groups; WHERE would filter individual source rows.
SELECT department,
       SUM(budget) AS total_budget,
       SUM(actual_cost) AS total_actual_cost,
       100.0 * SUM(actual_cost) / NULLIF(SUM(budget), 0) AS spend_percentage,
       SUM(actual_cost) > SUM(budget) AS over_budget
FROM dim_project
GROUP BY department
HAVING 1.0 * SUM(actual_cost) / NULLIF(SUM(budget), 0) > 0.90
ORDER BY spend_percentage DESC;

-- Q2
-- Join exactly one CURRENT employee version for present-day manager context.
-- Active projects mean In Progress. The task asks strictly more than THREE.
SELECT e.full_name, e.email,
       COUNT(*) AS active_project_count,
       SUM(p.budget) AS combined_budget_responsibility,
       SUM(p.actual_cost) AS combined_actual_spend
FROM dim_project p
JOIN dim_employee e ON e.employee_id = p.project_manager_id AND e.is_current = 1
WHERE p.status = 'In Progress'
GROUP BY e.employee_id, e.full_name, e.email
HAVING COUNT(*) > 3
ORDER BY active_project_count DESC, e.full_name;

-- Q3
-- Group by vendor KEY, not just name: suppliers sharing a name stay distinct.
-- The denominator includes ALL vendors, before applying the >5% filter.
WITH vendor_totals AS (
    SELECT vendor_key, SUM(amount) AS total_spend, COUNT(*) AS transaction_count
    FROM fact_transactions WHERE currency = 'AED'
    GROUP BY vendor_key
), vendor_shares AS (
    SELECT v.vendor_name, t.total_spend, t.transaction_count,
           100.0 * t.total_spend / NULLIF(SUM(t.total_spend) OVER (), 0) AS percentage_of_total_spend
    FROM vendor_totals t JOIN dim_vendor v USING (vendor_key)
)
SELECT vendor_name, total_spend, transaction_count, percentage_of_total_spend,
       CASE WHEN percentage_of_total_spend > 10 THEN 'HIGH'
            WHEN percentage_of_total_spend >= 5 THEN 'MEDIUM'
            ELSE 'NORMAL' END AS risk_flag
FROM vendor_shares
WHERE percentage_of_total_spend > 5
ORDER BY percentage_of_total_spend DESC;

-- Q4
-- Filter pending/disputed AED facts before grouping. NULL amounts are unknown;
-- COUNT still counts those transactions, whereas SUM ignores the missing amount.
SELECT p.project_id, p.project_name, p.department, p.status AS project_status,
       COUNT(*) AS open_transaction_count, SUM(t.amount) AS open_transaction_value
FROM fact_transactions t JOIN dim_project p USING (project_key)
WHERE t.payment_status IN ('Pending', 'Disputed') AND t.currency = 'AED'
GROUP BY p.project_key, p.project_id, p.project_name, p.department, p.status
HAVING SUM(t.amount) > 50000
ORDER BY open_transaction_value DESC;

-- Q5
-- Build a complete month/category grid so LAG means the previous CALENDAR month.
-- Include the full source date range; Pillar 2 does not limit this query to 12 months.
-- Missing month/category activity becomes zero, but missing source amounts remain unknown.
WITH monthly AS (
    SELECT SUBSTR(d.full_date, 1, 7) AS year_month, t.category, SUM(t.amount) AS monthly_spend
    FROM fact_transactions t JOIN dim_date d USING (date_key)
    WHERE t.currency = 'AED'
    GROUP BY SUBSTR(d.full_date, 1, 7), t.category
), months AS (
    SELECT DISTINCT SUBSTR(full_date, 1, 7) AS year_month FROM dim_date
    WHERE full_date BETWEEN
      (SELECT MIN(d.full_date) FROM fact_transactions t JOIN dim_date d USING(date_key)) AND
      (SELECT MAX(d.full_date) FROM fact_transactions t JOIN dim_date d USING(date_key))
), categories AS (
    SELECT DISTINCT category FROM fact_transactions WHERE currency = 'AED'
), grid AS (
    SELECT m.year_month, c.category,
           CASE WHEN x.year_month IS NULL THEN 0 ELSE x.monthly_spend END AS monthly_spend
    FROM months m CROSS JOIN categories c
    LEFT JOIN monthly x ON x.year_month = m.year_month AND x.category IS c.category
), trends AS (
    SELECT year_month, category, monthly_spend,
           SUM(monthly_spend) OVER (PARTITION BY category ORDER BY year_month
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total,
           LAG(monthly_spend) OVER (PARTITION BY category ORDER BY year_month) AS previous_month_spend
    FROM grid
)
SELECT year_month, category, monthly_spend, running_total,
       100.0 * (monthly_spend - previous_month_spend) / NULLIF(previous_month_spend, 0)
           AS month_over_month_pct_change
FROM trends
ORDER BY category, year_month;

-- Q6
-- Self-join adjacent versions: previous.valid_to equals new.valid_from.
-- This compares consecutive states, not every historical pair. Exclude unknown key 0.
-- Positive changes only; unchanged current-snapshot rows do not count as raises.
SELECT new.employee_id, new.full_name, new.valid_from AS change_date,
       previous.salary AS previous_salary, new.salary AS new_salary,
       new.salary - previous.salary AS increase_amount,
       100.0 * (new.salary - previous.salary) / NULLIF(previous.salary, 0) AS increase_pct
FROM dim_employee previous
JOIN dim_employee new ON new.employee_id = previous.employee_id
    AND previous.valid_to = new.valid_from
WHERE new.employee_key <> 0 AND new.salary > previous.salary
ORDER BY increase_amount DESC, new.employee_id, change_date
LIMIT 20;
