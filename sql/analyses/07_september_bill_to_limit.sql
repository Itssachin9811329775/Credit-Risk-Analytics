-- Question: How does observed default vary with September's statement-to-limit ratio?
-- Denominator: customers in each band; month is fixed before joining the outcome.
-- This is a recorded bill/limit ratio, not verified utilization, affordability, or recovery.
-- Negative bills are kept separate, and values at/above 100% are not clipped.
WITH ratios AS (
    SELECT c.customer_id, m.bill_amount_ntd,
           1.0 * m.bill_amount_ntd / c.credit_limit_ntd AS bill_to_limit
    FROM customers AS c
    JOIN monthly_repayments AS m ON m.customer_id = c.customer_id AND m.month = '2005-09'
), bands AS (
    SELECT customer_id,
           CASE WHEN bill_amount_ntd < 0 THEN 'Negative bill'
                WHEN bill_to_limit < 0.25 THEN '0-<25%'
                WHEN bill_to_limit < 0.50 THEN '25-<50%'
                WHEN bill_to_limit < 0.75 THEN '50-<75%'
                WHEN bill_to_limit < 1.00 THEN '75-<100%'
                ELSE '100%+' END AS bill_to_limit_band,
           CASE WHEN bill_amount_ntd < 0 THEN 1 WHEN bill_to_limit < 0.25 THEN 2
                WHEN bill_to_limit < 0.50 THEN 3 WHEN bill_to_limit < 0.75 THEN 4
                WHEN bill_to_limit < 1.00 THEN 5 ELSE 6 END AS sort_order
    FROM ratios
)
SELECT b.bill_to_limit_band, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM bands AS b
JOIN default_outcomes AS d ON d.customer_id = b.customer_id
GROUP BY b.bill_to_limit_band, b.sort_order ORDER BY b.sort_order;
