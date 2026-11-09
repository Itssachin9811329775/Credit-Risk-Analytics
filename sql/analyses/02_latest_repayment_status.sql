-- Question: How does observed default vary by the latest repayment status?
-- Denominator: customers in each September group; select one month BEFORE joining.
-- The -2 and 0 codes remain undocumented and are not assumed to be on time.
WITH september AS (
    SELECT customer_id,
           CASE WHEN repayment_status = -2 THEN 'Undocumented -2'
                WHEN repayment_status = -1 THEN 'Paid duly (-1)'
                WHEN repayment_status = 0 THEN 'Undocumented 0'
                WHEN repayment_status = 1 THEN '1 month delay'
                ELSE '2+ months delay' END AS status_group,
           CASE WHEN repayment_status = -2 THEN 1 WHEN repayment_status = -1 THEN 2
                WHEN repayment_status = 0 THEN 3 WHEN repayment_status = 1 THEN 4
                ELSE 5 END AS sort_order
    FROM monthly_repayments WHERE month = '2005-09'
)
SELECT s.status_group, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM september AS s
JOIN default_outcomes AS d ON d.customer_id = s.customer_id
GROUP BY s.status_group, s.sort_order
ORDER BY s.sort_order;
