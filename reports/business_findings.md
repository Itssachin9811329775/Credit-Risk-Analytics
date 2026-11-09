# Credit Risk & Repayment Behaviour Analytics: business findings

Generated from the validated UCI 350 dataset, with one row per customer.
Historical Taiwanese credit-card repayment history: April-September 2005;
target: the supplied next-month default flag. This is not Finnable data.

## Findings with denominators

1. **Portfolio baseline:** 6,636 of 30,000
   customers defaulted next month (22.12%).
2. **Recent recorded delay:** the September two-or-more-month delay group has
   2,177 defaults among 3,130 customers
   (69.55%), versus 16.78% among
   5,686 customers with documented paid-duly status. The delay
   group is 10.43% of customers and contains
   32.81% of observed defaults.
3. **Repeated recorded delays:** customers with three or more positive delay
   codes across the six months have 2,246 defaults among
   3,744 customers (59.99%). Those
   with no positive delay code have 2,334 defaults among
   19,931 (11.71%). The latter group
   includes undocumented codes and must not be labelled fully on-time.
4. **Credit-limit association:** below 50,000 NTD, the rate is
   36.07% (n=4,311); at least 200,000 NTD,
   it is 15.13% (n=11,150). This does not show
   that raising limits would reduce default; selection and omitted variables
   can explain differences.
5. **Zero recorded payments:** 544 of 1,432
   customers with zero payments in all six months defaulted
   (37.99%). Without contractual dues and transaction timing,
   zero payment is not proof of six missed required payments.
6. **Monthly comparability needs investigation:** code 1 appears for
   28 customers in August but
   3,688 in September. This
   distribution change is observable; its cause is not established. Do not
   interpret the rise in positive-delay share as proven portfolio deterioration
   without resolving code definitions and reporting timing.

These groups overlap. Their default counts must not be added. See the SQL
results and exploratory figures for mutually exclusive buckets and counts.
Wilson intervals in the plots describe sampling uncertainty within this
sample; they do not correct selection bias or establish transportability.

## Business recommendations to test

- **Pilot supportive early outreach** for customers with recent documented
  delays, with repeated delays as a secondary review signal. Compare eligible
  randomly assigned outreach and usual-process groups where operationally
  appropriate. Measure incremental resolution, successful contact, customer
  complaints, and cost per resolved account. This dataset cannot estimate that
  intervention's impact or ROI, so no uplift or savings are claimed.
- **Use repayment history alongside current account information**, rather
  than credit limits or demographic labels alone. A prioritisation rule in this
  project is an exploratory review aid, not an approved credit or collections
  policy. Check capacity, model calibration, segment stability, and fairness
  on representative current data before considering deployment.
- **Keep unknown states visible.** Obtain an authoritative data dictionary for
  repayment codes -2 and 0, and retain their separate dashboard categories until
  their meaning is resolved. Track undocumented-code coverage and negative bill
  values as quality indicators rather than silently deleting them.
- **Keep reporting denominators explicit.** Customer default metrics use
  unique customer outcomes. Monthly amounts use a selected month or an
  explicitly labelled sum of recorded payments; bill snapshots must not be
  summed across months as unique outstanding debt.

## What this project cannot establish

The sample is historical and comes from a different country and product
context. It is not representative evidence about Finnable borrowers. We have
no interest rates, contractual instalments, due dates, contact logs, recovery
actions, recoveries attributable to an action, income, or later cohorts.
Repayment-code delay categories are not exact days past due. Ratios of recorded
payments to same-month bills are not contractual repayment or recovery rates.

Observational associations do not prove causation. Many features are related,
so separate segment comparisons are not adjusted causal estimates. A random
customer split for the optional model cannot measure future-cohort drift.
The SQL heuristic's in-sample decile capture is distinct from held-out model
performance. No production underwriting system or live collection strategy
has been validated.

## Evidence and reproduction

- `reports/sql_results/`: all ten SQL result CSVs with group denominators.
- `reports/figures/`: labelled exploratory PNG charts.
- `reports/eda_summary.json`: numerical chart inputs and provenance.
- `reports/powerbi_export_validation.json`: Power BI handoff checks.
- `docs/data_source.md`: original source, licence, and checksums.
- Run `python -m src.run_project --offline` after installing core requirements.

Power BI export validation is separate from Desktop runtime verification.
See `powerbi/dashboard_guide.md` for the native report, and
`reports/project_status.json` for its current file/verification status.
The Python pipeline does not execute DAX or render Power BI visuals.
