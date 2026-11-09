-- Question: What is the size and observed next-month default rate of this sample?
-- Grain/denominator: one customer, using the two one-row-per-customer tables.
-- Credit limits are not outstanding balances, losses, or collections recovered.
SELECT COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       SUM(CASE WHEN d.default_next_month = 0 THEN 1 ELSE 0 END) AS nondefault_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate,
       SUM(c.credit_limit_ntd) AS total_credit_limit_ntd,
       AVG(c.credit_limit_ntd) AS mean_credit_limit_ntd
FROM customers AS c
JOIN default_outcomes AS d ON d.customer_id = c.customer_id;
