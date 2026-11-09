-- Question: Which August-to-September status transitions are associated with default?
-- Denominator: customers in each transition. Each customer contributes one fixed pair.
-- LAG is computed before filtering to September; otherwise the prior month disappears.
WITH ordered AS (
    SELECT customer_id, month, repayment_status,
           LAG(month) OVER (PARTITION BY customer_id ORDER BY month) AS previous_month,
           LAG(repayment_status) OVER (PARTITION BY customer_id ORDER BY month) AS previous_status
    FROM monthly_repayments
), transitions AS (
    SELECT customer_id,
           CASE WHEN previous_status = -2 THEN 'Undocumented -2'
                WHEN previous_status = -1 THEN 'Paid duly (-1)'
                WHEN previous_status = 0 THEN 'Undocumented 0'
                WHEN previous_status = 1 THEN '1 month delay'
                ELSE '2+ months delay' END AS august_status_group,
           CASE WHEN repayment_status = -2 THEN 'Undocumented -2'
                WHEN repayment_status = -1 THEN 'Paid duly (-1)'
                WHEN repayment_status = 0 THEN 'Undocumented 0'
                WHEN repayment_status = 1 THEN '1 month delay'
                ELSE '2+ months delay' END AS september_status_group
    FROM ordered WHERE month = '2005-09' AND previous_month = '2005-08'
)
SELECT t.august_status_group, t.september_status_group, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM transitions AS t
JOIN default_outcomes AS d ON d.customer_id = t.customer_id
GROUP BY t.august_status_group, t.september_status_group
ORDER BY t.august_status_group, t.september_status_group;
