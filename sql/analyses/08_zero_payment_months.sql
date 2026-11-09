-- Question: How does the count of months with zero recorded payment relate to default?
-- Denominator: customers grouped after six months are aggregated to one row each.
-- Zero recorded payment does NOT establish a missed contractual payment or failed collection.
WITH history AS (
    SELECT customer_id,
           SUM(CASE WHEN payment_amount_ntd = 0 THEN 1 ELSE 0 END) AS zero_payment_months
    FROM monthly_repayments GROUP BY customer_id
)
SELECT h.zero_payment_months, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate
FROM history AS h
JOIN default_outcomes AS d ON d.customer_id = h.customer_id
GROUP BY h.zero_payment_months ORDER BY h.zero_payment_months;
