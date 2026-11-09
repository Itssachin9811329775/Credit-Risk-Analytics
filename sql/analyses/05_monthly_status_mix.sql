-- Question: How does the observed repayment-status mix vary across the six months?
-- Denominator: the 30,000 customer-month rows WITHIN each month, not 180,000 customers.
-- 2+ delays are a subset of documented delays; never add these categories together.
-- No future outcome join is needed for this historical mix.
SELECT month, COUNT(*) AS customers,
       SUM(CASE WHEN repayment_status = -1 THEN 1 ELSE 0 END) AS paid_duly_customers,
       SUM(CASE WHEN repayment_status >= 1 THEN 1 ELSE 0 END) AS documented_delay_customers,
       SUM(CASE WHEN repayment_status >= 2 THEN 1 ELSE 0 END) AS two_plus_delay_customers,
       SUM(CASE WHEN repayment_status IN (-2, 0) THEN 1 ELSE 0 END) AS undocumented_customers,
       1.0 * SUM(CASE WHEN repayment_status >= 1 THEN 1 ELSE 0 END) / COUNT(*) AS documented_delay_share,
       1.0 * SUM(CASE WHEN repayment_status IN (-2, 0) THEN 1 ELSE 0 END) / COUNT(*) AS undocumented_share
FROM monthly_repayments GROUP BY month ORDER BY month;
