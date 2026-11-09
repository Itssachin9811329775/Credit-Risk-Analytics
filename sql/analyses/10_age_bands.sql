-- Question: What descriptive differences appear across broad age groups?
-- Denominator: customers per group, one row each. This is an audit/description only.
-- Do not turn demographic associations into automated lending or collections policy.
WITH bands AS (
    SELECT customer_id,
           CASE WHEN age < 30 THEN 'Under 30' WHEN age < 40 THEN '30-39'
                WHEN age < 50 THEN '40-49' ELSE '50+' END AS age_band,
           CASE WHEN age < 30 THEN 1 WHEN age < 40 THEN 2 WHEN age < 50 THEN 3 ELSE 4 END AS sort_order
    FROM customers
)
SELECT b.age_band, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM bands AS b
JOIN default_outcomes AS d ON d.customer_id = b.customer_id
GROUP BY b.age_band, b.sort_order ORDER BY b.sort_order;
