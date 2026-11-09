-- Question: How concentrated are observed defaults in an illustrative history-based ordering?
-- Denominator: customers per NTILE decile, 1 = highest priority under this fixed rule.
-- ORDERING USES NO OUTCOME: latest documented delay, delayed-month count, 2+ delay-month
-- count, then customer_id for deterministic ties. Undocumented latest codes receive no
-- documented-delay increment; this does NOT classify them as safe.
-- This is an in-sample exploratory queue, not a validated model, policy, or recovery estimate.
WITH history AS (
    SELECT customer_id,
           MAX(CASE WHEN month = '2005-09' AND repayment_status >= 1 THEN repayment_status ELSE 0 END) AS latest_documented_delay,
           SUM(CASE WHEN repayment_status >= 1 THEN 1 ELSE 0 END) AS delayed_months,
           SUM(CASE WHEN repayment_status >= 2 THEN 1 ELSE 0 END) AS two_plus_delayed_months
    FROM monthly_repayments GROUP BY customer_id
), ranked AS (
    SELECT customer_id, delayed_months,
           NTILE(10) OVER (ORDER BY latest_documented_delay DESC, delayed_months DESC,
                                   two_plus_delayed_months DESC, customer_id) AS priority_decile
    FROM history
), deciles AS (
    SELECT r.priority_decile, COUNT(*) AS customers,
           SUM(d.default_next_month) AS default_customers,
           AVG(r.delayed_months) AS mean_delayed_months
    FROM ranked AS r
    JOIN default_outcomes AS d ON d.customer_id = r.customer_id
    GROUP BY r.priority_decile
)
SELECT priority_decile, customers, default_customers,
       1.0 * default_customers / customers AS default_rate,
       1.0 * default_customers / SUM(default_customers) OVER () AS default_capture_share,
       1.0 * SUM(default_customers) OVER (ORDER BY priority_decile ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
           / SUM(default_customers) OVER () AS cumulative_default_capture_share,
       mean_delayed_months
FROM deciles ORDER BY priority_decile;
