"""Stage 7: write business findings from verified data after core outputs pass."""

import json
from datetime import datetime, timezone

from .analytics import load_analysis_data
from .download_data import PROJECT_ROOT


REPORT_DIR = PROJECT_ROOT / "reports"


def describe_cohort(features, mask):
    selected = features.loc[mask]
    defaults = int(selected.default_next_month.sum())
    return {"customers": len(selected), "defaults": defaults,
            "default_rate": defaults / len(selected),
            "customer_share": len(selected) / len(features),
            "default_capture_share": defaults / int(features.default_next_month.sum())}


def run():
    report = {"stage": 7, "status": "failed", "run_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        data = load_analysis_data()
        report["provenance"] = data["provenance"]
        for filename in ("sql_analysis.json", "eda_summary.json", "powerbi_export_validation.json"):
            prerequisite = json.loads((REPORT_DIR / filename).read_text(encoding="utf-8"))
            if prerequisite.get("status") != "passed":
                raise ValueError(f"{filename} must pass before stage 7.")
            if prerequisite["provenance"]["database_sha256"] != data["provenance"]["database_sha256"]:
                raise ValueError(f"{filename} describes a different database; rerun the core analysis.")
        f = data["customer_features"]
        cohorts = {
            "latest_two_plus_delay": describe_cohort(f, f.latest_repayment_status.ge(2)),
            "latest_paid_duly": describe_cohort(f, f.latest_repayment_status.eq(-1)),
            "three_plus_delay_months": describe_cohort(f, f.delayed_months.ge(3)),
            "no_recorded_positive_delay": describe_cohort(f, f.delayed_months.eq(0)),
            "zero_payment_all_six_months": describe_cohort(f, f.zero_payment_months.eq(6)),
            "credit_limit_below_50k": describe_cohort(f, f.credit_limit_ntd.lt(50_000)),
            "credit_limit_200k_plus": describe_cohort(f, f.credit_limit_ntd.ge(200_000)),
        }
        report["cohorts"] = cohorts
        report["portfolio"] = {"customers": len(f), "defaults": int(f.default_next_month.sum()),
                               "default_rate": float(f.default_next_month.mean())}
        monthly = data["monthly_repayments"]
        code_one_counts = monthly.loc[monthly.repayment_status.eq(1)].groupby("month").size()
        report["monthly_comparability"] = {"august_code_1": int(code_one_counts.loc["2005-08"]),
                                           "september_code_1": int(code_one_counts.loc["2005-09"])}
        recent, repeated = cohorts["latest_two_plus_delay"], cohorts["three_plus_delay_months"]
        paid, no_delay = cohorts["latest_paid_duly"], cohorts["no_recorded_positive_delay"]
        low, high = cohorts["credit_limit_below_50k"], cohorts["credit_limit_200k_plus"]
        zero = cohorts["zero_payment_all_six_months"]
        content = f"""# Credit Risk & Repayment Behaviour Analytics: business findings

Generated from the validated UCI 350 dataset, with one row per customer.
Historical Taiwanese credit-card repayment history: April-September 2005;
target: the supplied next-month default flag. This is not Finnable data.

## Findings with denominators

1. **Portfolio baseline:** {int(f.default_next_month.sum()):,} of {len(f):,}
   customers defaulted next month ({f.default_next_month.mean():.2%}).
2. **Recent recorded delay:** the September two-or-more-month delay group has
   {recent['defaults']:,} defaults among {recent['customers']:,} customers
   ({recent['default_rate']:.2%}), versus {paid['default_rate']:.2%} among
   {paid['customers']:,} customers with documented paid-duly status. The delay
   group is {recent['customer_share']:.2%} of customers and contains
   {recent['default_capture_share']:.2%} of observed defaults.
3. **Repeated recorded delays:** customers with three or more positive delay
   codes across the six months have {repeated['defaults']:,} defaults among
   {repeated['customers']:,} customers ({repeated['default_rate']:.2%}). Those
   with no positive delay code have {no_delay['defaults']:,} defaults among
   {no_delay['customers']:,} ({no_delay['default_rate']:.2%}). The latter group
   includes undocumented codes and must not be labelled fully on-time.
4. **Credit-limit association:** below 50,000 NTD, the rate is
   {low['default_rate']:.2%} (n={low['customers']:,}); at least 200,000 NTD,
   it is {high['default_rate']:.2%} (n={high['customers']:,}). This does not show
   that raising limits would reduce default; selection and omitted variables
   can explain differences.
5. **Zero recorded payments:** {zero['defaults']:,} of {zero['customers']:,}
   customers with zero payments in all six months defaulted
   ({zero['default_rate']:.2%}). Without contractual dues and transaction timing,
   zero payment is not proof of six missed required payments.
6. **Monthly comparability needs investigation:** code 1 appears for
   {report['monthly_comparability']['august_code_1']:,} customers in August but
   {report['monthly_comparability']['september_code_1']:,} in September. This
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
"""
        (REPORT_DIR / "business_findings.md").write_text(content, encoding="utf-8")
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        (REPORT_DIR / "business_findings.md").write_text(
            "# Business findings need regeneration\n\nA prerequisite failed. See findings.json.\n", encoding="utf-8")
        raise
    finally:
        (REPORT_DIR / "findings.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Stage 7 passed: evidence-based findings and business recommendations written.")


if __name__ == "__main__":
    run()
