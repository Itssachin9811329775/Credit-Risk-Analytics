# Stage 5: exploratory analysis and charts

Run from the project root in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.explore_data
```

The command validates the source and database, builds customer-level history
features, and writes seven PNG charts plus `reports/eda_summary.json` and
`reports/stage_05_summary.md`. It is offline and requires no new packages.

## Read the charts

1. `01_default_outcomes.png`: customer counts for the single next-month outcome;
   each of the 30,000 customers contributes once.
2. `02_latest_status_default_rate.png`: default rates within September repayment
   categories, with segment size and 95% Wilson intervals. Undocumented codes
   -2 and 0 remain separate from paid-duly and documented delay.
3. `03_delayed_months_default_rate.png`: default rates by the number of history
   months with a documented delay code of at least 1. A zero count does not mean
   six on-time payments, because undocumented codes may be present.
4. `04_monthly_status_mix.png`: the share of each month's 30,000 customers in
   paid-duly, documented-delay, and undocumented states. The same customers
   appear over time; these are not six independent customer samples. One-month
   delay code 1 appears for 28 customers in August versus 3,688 in September.
   Review documentation and timing before calling the changing mix portfolio
   deterioration.
5. `05_credit_limit_default_rate.png`: rates within fixed descriptive credit
   bands, in New Taiwan dollars. Credit limits are not outstanding debt.
6. `06_zero_payment_default_rate.png`: rates by the number of months with a
   recorded zero payment. No contractual payment due field is available, so
   these cannot be labelled missed-payment counts or collection failure rates.
7. `07_aug_sep_transitions.png`: conditional transitions from August to September
   repayment groups. Each row totals 100%, using the August group's customer
   count as denominator. Every cell also shows its observed count.

The source time window and metric units appear on every chart. No outlier
clipping or invented values are used. The JSON stores all plotted rates,
counts, interval limits, monthly shares, and transition counts, together with
source provenance and PNG hashes. If a run fails, read the JSON status before
using existing figures, which may belong to a previous successful run.

## Statistical interpretation

Wilson intervals express binomial sampling uncertainty around each segment's
observed default rate. They are not proof of causal effects, do not adjust for
confounding or multiple exploratory comparisons, and do not make this historical
sample representative of current Indian lending customers. Segment size is
shown because a rate based on a small group is less stable.

The September group with at least two months' documented delay has 2,177 defaults
among 3,130 customers (69.55%). The paid-duly code -1 group has 954 defaults among
5,686 customers (16.78%). This supports investigating repayment history as an
associated risk indicator. It does not establish that any collections action
would reduce defaults. Current portfolio validation and an intervention study
would be needed before recommending operational thresholds.

## How to defend the analysis

"I aggregated monthly history before joining the customer outcome. I reported
segment counts with rates and uncertainty, kept undocumented codes separate,
and checked denominators independently. I used the charts to identify patterns
worth investigating, not to claim causes or collection-policy improvements."

Run the focused checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_exploration.py -v
```
