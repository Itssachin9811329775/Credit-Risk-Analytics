-- Question: How does observed default differ across given credit-limit bands?
-- Denominator: customers per band; NTD boundaries are fixed descriptive choices.
-- This association does not show that changing a limit changes default risk.
WITH bands AS (
    SELECT customer_id,
           CASE WHEN credit_limit_ntd < 50000 THEN 'Below 50k'
                WHEN credit_limit_ntd < 100000 THEN '50k-<100k'
                WHEN credit_limit_ntd < 200000 THEN '100k-<200k'
                ELSE '200k+' END AS credit_limit_band,
           CASE WHEN credit_limit_ntd < 50000 THEN 1 WHEN credit_limit_ntd < 100000 THEN 2
                WHEN credit_limit_ntd < 200000 THEN 3 ELSE 4 END AS sort_order
    FROM customers
)
SELECT b.credit_limit_band, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM bands AS b
JOIN default_outcomes AS d ON d.customer_id = b.customer_id
GROUP BY b.credit_limit_band, b.sort_order
ORDER BY b.sort_order;
