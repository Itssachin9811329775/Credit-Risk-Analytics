-- Stage-3 diagnostic, not one of the ten stage-4 business analyses.
-- The direct join deliberately demonstrates duplicated customer-level sums.
-- All six months exist here; a matching AVG(default) would NOT prove a safe grain.
WITH monthly_summary AS (
    SELECT customer_id, COUNT(*) AS history_months
    FROM monthly_repayments
    GROUP BY customer_id
)
SELECT 'customer_tables' AS join_pattern,
       COUNT(*) AS row_count,
       COUNT(DISTINCT c.customer_id) AS unique_customers,
       SUM(c.credit_limit_ntd) AS credit_limit_sum_ntd,
       SUM(d.default_next_month) AS default_count
FROM customers AS c
JOIN default_outcomes AS d ON d.customer_id = c.customer_id

UNION ALL

SELECT 'direct_monthly_join', COUNT(*), COUNT(DISTINCT c.customer_id),
       SUM(c.credit_limit_ntd), SUM(d.default_next_month)
FROM customers AS c
JOIN default_outcomes AS d ON d.customer_id = c.customer_id
JOIN monthly_repayments AS m ON m.customer_id = c.customer_id

UNION ALL

SELECT 'aggregate_before_join', COUNT(*), COUNT(DISTINCT c.customer_id),
       SUM(c.credit_limit_ntd), SUM(d.default_next_month)
FROM customers AS c
JOIN default_outcomes AS d ON d.customer_id = c.customer_id
JOIN monthly_summary AS m ON m.customer_id = c.customer_id;
