"""Run ten SQL business analyses and reconcile them independently with Pandas."""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .analytics import load_analysis_data, status_group
from .build_database import DATABASE_PATH, connect_database
from .download_data import PROJECT_ROOT, sha256


SQL_DIR = PROJECT_ROOT / "sql" / "analyses"
RESULT_DIR = PROJECT_ROOT / "reports" / "sql_results"
REPORT_PATH = PROJECT_ROOT / "reports" / "sql_analysis.json"
QUERY_KEYS = {
    "01_portfolio_overview": [],
    "02_latest_repayment_status": ["status_group"],
    "03_credit_limit_bands": ["credit_limit_band"],
    "04_delayed_month_count": ["delayed_months"],
    "05_monthly_status_mix": ["month"],
    "06_aug_sep_transitions": ["august_status_group", "september_status_group"],
    "07_september_bill_to_limit": ["bill_to_limit_band"],
    "08_zero_payment_months": ["zero_payment_months"],
    "09_history_priority_deciles": ["priority_decile"],
    "10_age_bands": ["age_band"],
}


def grouped_defaults(frame, keys):
    """Keep the numerator and denominator visible when computing a segment rate."""
    grouped = frame.groupby(keys, as_index=False, observed=True).agg(
        customers=("customer_id", "size"), default_customers=("default_next_month", "sum")
    )
    grouped["default_rate"] = grouped.default_customers / grouped.customers
    return grouped


def bill_ratio_band(value):
    if value < 0:
        return "Negative bill"
    for upper, label in ((0.25, "0-<25%"), (0.50, "25-<50%"), (0.75, "50-<75%"), (1.00, "75-<100%")):
        if value < upper:
            return label
    return "100%+"


def pandas_references(data):
    """An independent dataframe route to the same answers checks the SQL logic."""
    features = data["customer_features"]
    monthly = data["monthly_repayments"]
    defaults = int(features.default_next_month.sum())
    references = {
        "01_portfolio_overview": pd.DataFrame([{
            "customers": len(features), "default_customers": defaults,
            "nondefault_customers": len(features) - defaults,
            "default_rate": defaults / len(features),
            "total_credit_limit_ntd": int(features.credit_limit_ntd.sum()),
            "mean_credit_limit_ntd": float(features.credit_limit_ntd.mean()),
        }]),
        "02_latest_repayment_status": grouped_defaults(features.rename(columns={"latest_status_group": "status_group"}), ["status_group"]),
        "03_credit_limit_bands": grouped_defaults(features, ["credit_limit_band"]),
        "08_zero_payment_months": grouped_defaults(features, ["zero_payment_months"]),
        "10_age_bands": grouped_defaults(features, ["age_band"]),
    }
    delayed = grouped_defaults(features, ["delayed_months"])
    unknown = features.groupby("delayed_months", as_index=False).unknown_status_months.mean().rename(
        columns={"unknown_status_months": "mean_undocumented_months"})
    references["04_delayed_month_count"] = delayed.merge(unknown, on="delayed_months", validate="one_to_one")

    mix = monthly.assign(paid_duly=monthly.repayment_status.eq(-1),
                         documented_delay=monthly.repayment_status.ge(1),
                         two_plus_delay=monthly.repayment_status.ge(2),
                         undocumented=monthly.repayment_status.isin([-2, 0]))
    mix = mix.groupby("month", as_index=False).agg(
        customers=("customer_id", "size"), paid_duly_customers=("paid_duly", "sum"),
        documented_delay_customers=("documented_delay", "sum"),
        two_plus_delay_customers=("two_plus_delay", "sum"), undocumented_customers=("undocumented", "sum"))
    mix["documented_delay_share"] = mix.documented_delay_customers / mix.customers
    mix["undocumented_share"] = mix.undocumented_customers / mix.customers
    references["05_monthly_status_mix"] = mix

    # Pivoting fixed months checks the SQL LAG route without using a SQL window.
    pair = monthly.loc[monthly.month.isin(["2005-08", "2005-09"])].pivot(
        index="customer_id", columns="month", values="repayment_status").reset_index()
    pair["august_status_group"] = pair["2005-08"].map(status_group)
    pair["september_status_group"] = pair["2005-09"].map(status_group)
    pair = pair.merge(data["default_outcomes"], on="customer_id", validate="one_to_one")
    references["06_aug_sep_transitions"] = grouped_defaults(pair, ["august_status_group", "september_status_group"])

    ratios = features.assign(bill_to_limit_band=features.latest_bill_to_limit.map(bill_ratio_band))
    references["07_september_bill_to_limit"] = grouped_defaults(ratios, ["bill_to_limit_band"])

    ranked = features.assign(latest_documented_delay=features.latest_repayment_status.clip(lower=0)).sort_values(
        ["latest_documented_delay", "delayed_months", "severe_delay_months", "customer_id"],
        ascending=[False, False, False, True]).reset_index(drop=True)
    # NTILE distributes any remainder among the first buckets.
    bucket_size, extra = divmod(len(ranked), 10)
    ranked["priority_decile"] = np.repeat(np.arange(1, 11), [bucket_size + (i < extra) for i in range(10)])
    deciles = grouped_defaults(ranked, ["priority_decile"])
    deciles["default_capture_share"] = deciles.default_customers / defaults
    deciles["cumulative_default_capture_share"] = deciles.default_capture_share.cumsum()
    mean_delay = ranked.groupby("priority_decile", as_index=False).delayed_months.mean().rename(
        columns={"delayed_months": "mean_delayed_months"})
    references["09_history_priority_deciles"] = deciles.merge(mean_delay, on="priority_decile", validate="one_to_one")
    return references


def execute_queries(connection):
    paths = sorted(SQL_DIR.glob("*.sql"))
    if [path.stem for path in paths] != list(QUERY_KEYS):
        raise ValueError("Expected exactly the ten documented SQL analysis files.")
    return {path.stem: pd.read_sql_query(path.read_text(encoding="utf-8"), connection) for path in paths}


def validate_results(results, data):
    references = pandas_references(data)
    checks = []
    if set(results) != set(QUERY_KEYS):
        raise ValueError("Missing or unexpected SQL analysis results.")
    for name, keys in QUERY_KEYS.items():
        actual = results[name]
        expected = references[name]
        if actual.empty or actual.isna().any().any():
            raise ValueError(f"{name}: empty or missing result values")
        if keys and actual.duplicated(keys).any():
            raise ValueError(f"{name}: duplicate segment keys")
        if keys:
            actual = actual.sort_values(keys).reset_index(drop=True)
            expected = expected.sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-12, atol=1e-12)
        checks.append({"analysis": name, "passed": True,
                       "detail": "Every SQL count, total, rate, and grouping matches independent Pandas calculations"})
    return checks


def run():
    report = {"stage": 4, "status": "failed", "run_at_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = load_analysis_data()
        report["provenance"] = data["provenance"]
        connection = connect_database(DATABASE_PATH, readonly=True)
        try:
            results = execute_queries(connection)
        finally:
            connection.close()
        report["checks"] = validate_results(results, data)
        # All results are reconciled before any result CSV is published.
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        report["results"] = {}
        for name, frame in results.items():
            output = RESULT_DIR / f"{name}.csv"
            temporary = output.with_suffix(".csv.tmp")
            frame.to_csv(temporary, index=False, encoding="utf-8")
            temporary.replace(output)
            report["results"][name] = {
                "columns": list(frame.columns), "row_count": len(frame),
                "records": json.loads(frame.to_json(orient="records", double_precision=15)),
                "csv_path": output.relative_to(PROJECT_ROOT).as_posix(),
                "sql_sha256": sha256((SQL_DIR / f"{name}.sql").read_bytes()),
                "csv_sha256": sha256(output.read_bytes()),
            }
        report["query_count"] = len(results)
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Stage 4 passed: {report['query_count']} SQL analyses independently reconciled with Pandas.")
    print(f"Results: {RESULT_DIR}")
    return report


if __name__ == "__main__":
    run()
