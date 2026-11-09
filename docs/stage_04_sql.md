# Stage 4: ten business questions in SQL

The ten queries in `sql/analyses/` run against the real SQLite database. Every
count, rate, and monetary total is independently reconciled with Pandas before
the runner publishes result CSVs. These are descriptive analyses of the UCI
sample, not estimates of Finnable's current customers or causal effects.

## Run the analyses

From the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.run_sql_analysis
```

The command validates the upstream source and database, executes all ten
queries through a read-only connection, and writes:

- `reports/sql_results/01_portfolio_overview.csv` through the ten named CSVs.
- `reports/sql_analysis.json`, containing status, source provenance, query and
  output checksums, reconciliation checks, and all result records.

All rate/share fields are fractions between 0 and 1. Display `0.2212` as 22.12%.
On failure, the JSON report is marked failed; any old CSVs must not be treated
as a successful new run. The script does not change the database.

## Questions, grain, and SQL techniques

1. **Portfolio overview** (`01_portfolio_overview.sql`). Count customers,
   defaults, and credit limits using the two customer-grain tables. A JOIN and
   CASE establish the baseline denominator of 30,000 customers. Credit limits
   are not outstanding debt or losses.
2. **Latest repayment status** (`02_latest_repayment_status.sql`). Filter to
   September before joining the outcome; CASE creates five explicit groups.
   The denominator is customers in each group. The -2 and 0 codes are kept
   separate and are not labelled safe or on-time.
3. **Credit-limit bands** (`03_credit_limit_bands.sql`). A CTE and CASE assign
   fixed NTD bands. Boundaries are lower-inclusive: 50,000 enters `50k-<100k`.
   Each customer appears once. An association does not justify changing limits.
4. **Repeated documented delay** (`04_delayed_month_count.sql`). Aggregate the
   six months to a customer first, then join the future outcome. Count statuses
   at least 1 as documented delay and report average undocumented months too.
   Zero documented delays is not equivalent to six paid-duly months.
5. **Monthly status mix** (`05_monthly_status_mix.sql`). Conditional aggregation
   counts paid-duly, documented-delay, and undocumented statuses within each
   month. Each denominator is 30,000. The 2+ delay count is a subset of documented
   delay, so adding both would double-count customers.
6. **August-to-September transitions** (`06_aug_sep_transitions.sql`). `LAG`
   operates on the full ordered history before September is selected. Filtering
   to September inside the window's input would remove August. Each customer
   contributes one fixed pair, and the denominator is that transition's size.
7. **September bill-to-limit ratio** (`07_september_bill_to_limit.sql`). Join
   one month to customer limits, then use CASE bands. Negative statements get
   their own group, and ratios at or above 100% remain visible. This is a
   recorded statement/limit ratio, not a verified affordability or recovery rate.
8. **Zero recorded payments** (`08_zero_payment_months.sql`). A customer-level
   CTE counts zero-payment months before joining outcomes. Zero recorded payment
   alone does not prove a missed contractual instalment; contractual dues are
   not supplied.
9. **Illustrative priority deciles** (`09_history_priority_deciles.sql`).
   `NTILE(10)` ranks customers by latest documented delay, number of delayed
   months, number of 2+ delay months, and customer ID for deterministic ties.
   The future outcome is joined only after ranking. Window sums calculate each
   decile's share of defaults and cumulative capture. This is an in-sample
   exploratory queue, not a trained or validated model or a deployment policy.
   Customer ID is only a tie breaker, not evidence of risk. Lower deciles with
   identical history scores should not be interpreted as distinct risk levels.
10. **Age-band audit** (`10_age_bands.sql`). Describe broad age groups with CASE
    and a customer-grain join. This is a descriptive audit, not a recommendation
    to discriminate or use age as an automated decision rule.

## Actual results to discuss

The results below were calculated from the downloaded source, with no rows
fabricated or removed:

- The sample has **6,636 defaults among 30,000 customers: 22.12%**.
- September's **2+ months delay** group has **2,177 defaults among 3,130 customers
  (69.55%)**. The documented paid-duly group has **954 among 5,686 (16.78%)**.
  The difference is an association that can motivate a prospective monitoring
  test; it does not show that a particular intervention works.
- Customers with six documented-delay months have **943 defaults among 1,341
  (70.32%)**, versus **2,334 among 19,931 (11.71%)** with no documented-delay
  months. The latter group averages **4.66 undocumented-code months**, so calling
  it always on-time would misrepresent the data.
- The illustrative first decile contains **3,000 customers and 2,098 defaults**:
  **31.62% of this sample's defaults** in 10% of customers. This is exploratory
  in-sample concentration, not held-out model performance or expected collections
  recovery. Operational queue rules need validation on new customers and costs.
- Credit limits below 50,000 NTD have **1,555 / 4,311 defaults (36.07%)**, versus
  **1,687 / 11,150 (15.13%)** at 200,000 NTD and above. Borrower selection and
  other unobserved differences may explain the association; raising a limit is
  not an evidenced risk-reduction strategy.

Treat monthly comparisons cautiously. September's documented-delay share is
22.73%, compared with 14.79% in August, but the count in code 1 alone changes
from 28 to 3,688. This conspicuous distribution difference warrants investigation
of reporting and code comparability; the file does not establish its cause.

## Correctness checks

Pandas uses customer-level groupings, a fixed-month pivot for transitions, and
an independently sorted ordering for deciles. The runner compares every result
cell to SQL, allowing only tiny floating-point rounding differences. Segment
keys must be unique and results must be nonempty and complete.

The SQL regression tests verify full customer/default partitions, weighted
rates, monthly category coverage, transition reconciliation, decile capture,
negative-bill retention, and rejection of plausible-looking corrupted counts.

```powershell
.\.venv\Scripts\python.exe -W error -m unittest discover -s tests -p 'test_sql_analysis.py' -v
```

## Interview explanation

"I wrote ten queries around explicit business questions and stated each
denominator. For customer risk metrics I selected a single month or aggregated
the history before joining the outcome. I used LAG for a fixed month-to-month
transition and NTILE for an illustrative history-only queue. I checked every
SQL result independently in Pandas and reported counts alongside percentages.
The results suggest hypotheses to test, not causal claims or Finnable findings."
