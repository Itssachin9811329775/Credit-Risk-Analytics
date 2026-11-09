"""Stage 6: export validated CSV tables and reference checks for Power BI.

This creates a data/model handoff, not a Power BI report or an executed DAX model.
Run from the project root with: python -m src.export_powerbi
"""

import json
from datetime import datetime, timezone

import pandas as pd

from .analytics import AGE_BANDS, CREDIT_BANDS, STATUS_GROUPS, load_analysis_data, status_group
from .download_data import PROJECT_ROOT, sha256
from .prepare_data import check


EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
REPORT_PATH = PROJECT_ROOT / "reports" / "powerbi_export_validation.json"


def make_exports(data):
    """Keep the customer dimension separate from the single future outcome."""
    customers = data["customer_features"].drop(columns="default_next_month").copy()
    for column, levels in (("credit_limit_band", CREDIT_BANDS), ("age_band", AGE_BANDS),
                           ("latest_status_group", STATUS_GROUPS)):
        customers[f"{column}_order"] = customers[column].map({label: i + 1 for i, label in enumerate(levels)})

    monthly = data["monthly_repayments"].copy()
    monthly["month_start"] = monthly["month"] + "-01"
    monthly["repayment_status_group"] = monthly.repayment_status.map(status_group)
    calendar = pd.DataFrame({"month": sorted(monthly.month.unique())})
    calendar["month_start"] = calendar["month"] + "-01"
    calendar["month_label"] = pd.to_datetime(calendar.month_start).dt.strftime("%b %Y")
    calendar["month_order"] = calendar["month"].str.replace("-", "", regex=False).astype("int64")
    return {
        "customers": customers.sort_values("customer_id").reset_index(drop=True),
        "monthly_repayments": monthly.sort_values(["customer_id", "month"]).reset_index(drop=True),
        "default_outcomes": data["default_outcomes"].sort_values("customer_id").reset_index(drop=True),
        "calendar_months": calendar,
    }


def reference_metrics(tables, customer_ids=None, months=None, status_groups=None):
    """Independent Python reference for the documented single-direction model.

    Customer filters reach both facts. History filters affect monthly rows only;
    cohort metrics explicitly transfer the visible monthly customer IDs to the
    outcome table. These checks do not execute DAX.
    """
    customers = tables["customers"]
    if customer_ids is not None:
        customers = customers.loc[customers.customer_id.isin(customer_ids)]
    outcomes = tables["default_outcomes"].loc[lambda frame: frame.customer_id.isin(customers.customer_id)]
    monthly = tables["monthly_repayments"].loc[lambda frame: frame.customer_id.isin(customers.customer_id)]
    if months is not None:
        monthly = monthly.loc[monthly.month.isin(months)]
    if status_groups is not None:
        monthly = monthly.loc[monthly.repayment_status_group.isin(status_groups)]
    cohort_ids = monthly.customer_id.unique()
    cohort = outcomes.loc[outcomes.customer_id.isin(cohort_ids)]
    selected_months = set(tables["calendar_months"].month) if months is None else set(months)
    return {
        "customer_count": len(customers),
        "outcome_customers": len(outcomes),
        "defaulting_customers": int(outcomes.default_next_month.sum()),
        "default_rate": float(outcomes.default_next_month.mean()) if len(outcomes) else None,
        "credit_limit_ntd": int(customers.credit_limit_ntd.sum()),
        "monthly_rows": len(monthly),
        "monthly_customers": int(monthly.customer_id.nunique()),
        "documented_delay_rows": int(monthly.repayment_status.ge(1).sum()),
        "undocumented_status_rows": int(monthly.repayment_status.isin([-2, 0]).sum()),
        "paid_duly_rows": int(monthly.repayment_status.eq(-1).sum()),
        "recorded_payments_ntd": int(monthly.payment_amount_ntd.sum()),
        "single_month_bill_ntd": int(monthly.bill_amount_ntd.sum()) if len(selected_months) == 1 else None,
        "cohort_customers": len(cohort_ids),
        "cohort_defaulting_customers": int(cohort.default_next_month.sum()),
        "cohort_default_rate": float(cohort.default_next_month.mean()) if len(cohort) else None,
    }


def validate_exports(tables, data, report):
    customers, monthly, outcomes, calendar = [tables[name] for name in
                                             ("customers", "monthly_repayments", "default_outcomes", "calendar_months")]
    check(report, "Customer dimension key", customers.customer_id.is_unique and len(customers) == len(data["customers"]),
          f"{len(customers):,} unique customers")
    check(report, "Target separated from history", "default_next_month" not in customers and "default_next_month" not in monthly,
          "Only default_outcomes contains the future target")
    check(report, "Outcome key and coverage", outcomes.customer_id.is_unique and set(outcomes.customer_id) == set(customers.customer_id),
          "One future outcome per customer")
    check(report, "Customer-month key", not monthly.duplicated(["customer_id", "month_start"]).any(),
          "No duplicate customer-month pairs")
    check(report, "Monthly foreign-key coverage", set(monthly.customer_id) == set(customers.customer_id),
          "Every monthly customer exists in the dimension, and every customer has history")
    check(report, "Calendar key and coverage", calendar.month_start.is_unique and len(calendar) == 6
          and set(calendar.month_start) == set(monthly.month_start), "Six unique first-of-month grouping keys")
    check(report, "Monthly histories complete", len(monthly) == len(customers) * 6
          and monthly.groupby("customer_id").month.nunique().eq(6).all(), "Six months per customer")
    check(report, "No missing export values", all(not frame.isna().any().any() for frame in tables.values()),
          "No missing keys, values, labels, or ordering fields")
    check(report, "Original customer values preserved", customers[data["customers"].columns].equals(data["customers"]),
          "Customer labels, raw codes, monetary values, and flags match SQLite")
    check(report, "Original monthly values preserved", monthly[data["monthly_repayments"].columns].equals(data["monthly_repayments"]),
          "All 180,000 source monthly records match SQLite")
    check(report, "Original outcomes preserved", outcomes.equals(data["default_outcomes"]), "All customer outcomes match SQLite")
    history_totals = monthly.groupby("customer_id").payment_amount_ntd.sum().sort_index()
    check(report, "Customer payment totals reconcile", history_totals.equals(customers.set_index("customer_id").total_payment_ntd.sort_index()),
          "Customer-level six-month payment sums match monthly history")

    scenarios = {
        "unfiltered": reference_metrics(tables),
        "september_only": reference_metrics(tables, months=["2005-09"]),
        "september_two_plus_delay": reference_metrics(tables, months=["2005-09"], status_groups=["2+ months delay"]),
        "below_50k_september_two_plus_delay": reference_metrics(
            tables, customer_ids=customers.loc[customers.credit_limit_band.eq("Below 50k"), "customer_id"],
            months=["2005-09"], status_groups=["2+ months delay"]),
    }
    report["reference_scenarios"] = scenarios
    baseline = scenarios["unfiltered"]
    september = scenarios["september_only"]
    severe = scenarios["september_two_plus_delay"]
    check(report, "History filters do not redefine base outcome", baseline["default_rate"] == september["default_rate"] == severe["default_rate"]
          and baseline["customer_count"] == severe["customer_count"], "Month/status filters require explicit cohort metrics to affect outcome cards")
    check(report, "Single-month bill guard", baseline["single_month_bill_ntd"] is None and september["single_month_bill_ntd"] is not None,
          "Bill snapshots are not summed across history months")
    latest_severe = data["customer_features"].loc[data["customer_features"].latest_repayment_status.ge(2)]
    check(report, "Selected cohort reconciles independently", severe["cohort_customers"] == len(latest_severe)
          and severe["cohort_defaulting_customers"] == int(latest_severe.default_next_month.sum()),
          "The September 2+ delay cohort agrees with the independent customer feature table")
    check(report, "Monthly status states partition rows", all(item["documented_delay_rows"] + item["undocumented_status_rows"]
          + item["paid_duly_rows"] == item["monthly_rows"] for item in scenarios.values()), "Documented delay, paid duly, and undocumented are separate")


def run():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {"stage": 6, "status": "failed", "run_at_utc": datetime.now(timezone.utc).isoformat(), "checks": [],
              "power_bi_status": "This step validates CSV exports only. Desktop runtime evidence is recorded separately in reports/powerbi_runtime_validation.json."}
    pending = []
    try:
        data = load_analysis_data()
        report["provenance"] = data["provenance"]
        tables = make_exports(data)
        validate_exports(tables, data, report)
        for name, frame in tables.items():
            path = EXPORT_DIR / f"{name}.csv"
            temporary = path.with_suffix(".csv.tmp")
            frame.to_csv(temporary, index=False, encoding="utf-8")
            reread = pd.read_csv(temporary, float_precision="round_trip")
            check(report, f"{name}: CSV round-trip", frame.equals(reread), "All columns, types, and values survive export")
            pending.append((temporary, path))
        report["outputs"] = {}
        for temporary, path in pending:
            temporary.replace(path)
            frame = tables[path.stem]
            report["outputs"][path.stem] = {"path": path.relative_to(PROJECT_ROOT).as_posix(), "rows": len(frame),
                                             "columns": list(frame.columns), "sha256": sha256(path.read_bytes())}
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Stage 6 export checks passed: {len(report['checks'])} checks; four CSV tables.")
    print(f"Exports: {EXPORT_DIR}")
    print("CSV validation only. See powerbi/dashboard_guide.md for the report and Desktop checks.")
    return report


if __name__ == "__main__":
    run()
