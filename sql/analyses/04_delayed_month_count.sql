-- Question: Is repeated documented delay associated with next-month default?
-- Denominator: customers grouped by number of months with status >= 1.
-- Zero documented delays does not mean six on-time months: -2/0 are undocumented.
WITH history AS (
    SELECT customer_id,
           SUM(CASE WHEN repayment_status >= 1 THEN 1 ELSE 0 END) AS delayed_months,
           SUM(CASE WHEN repayment_status IN (-2, 0) THEN 1 ELSE 0 END) AS undocumented_months
    FROM monthly_repayments GROUP BY customer_id
)
SELECT h.delayed_months, COUNT(*) AS customers,
       SUM(d.default_next_month) AS default_customers,
       1.0 * SUM(d.default_next_month) / COUNT(*) AS default_rate,
       AVG(h.undocumented_months) AS mean_undocumented_months
FROM history AS h
JOIN default_outcomes AS d ON d.customer_id = h.customer_id
GROUP BY h.delayed_months ORDER BY h.delayed_months;
