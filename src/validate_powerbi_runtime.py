"""Reconcile actual Desktop DAX results against the exported data using Pandas.

1. python -m src.validate_powerbi_runtime --prepare
2. Run scripts/query_powerbi_model.ps1 against the open model (see its parameters).
3. python -m src.validate_powerbi_runtime

This validator never substitutes Python values for actual Power BI results.
"""

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone

import pandas as pd

from .download_data import PROJECT_ROOT
from .export_powerbi import reference_metrics


QUERY = PROJECT_ROOT / "powerbi" / "validation_all_measures.dax"
RESULTS = PROJECT_ROOT / "reports" / "powerbi_all_measures_results.json"
REPORT = PROJECT_ROOT / "reports" / "powerbi_dax_validation.json"

# Explicit aliases make both the generated query and the comparison readable.
MEASURES = {
    "customer_count": "Customer Count",
    "outcome_customers": "Outcome Customers",
    "defaulting_customers": "Defaulting Customers",
    "default_rate": "Default Rate",
    "credit_limit_ntd": "Credit Limit NTD",
    "monthly_rows": "Monthly Rows",
    "monthly_customers": "Monthly Customers",
    "documented_delay_rows": "Documented Delay Rows",
    "documented_delay_share": "Documented Delay Share",
    "undocumented_status_rows": "Undocumented Status Rows",
    "undocumented_status_share": "Undocumented Status Share",
    "recorded_payments_ntd": "Recorded Payments NTD",
    "single_month_bill_ntd": "Single Month Bill NTD",
    "negative_bill_rows": "Negative Bill Rows",
    "cohort_customers": "Selected History Customers",
    "cohort_defaulting_customers": "Defaults in Selected History Cohort",
    "cohort_default_rate": "Selected History Cohort Default Rate",
    "cohort_credit_limit_ntd": "Credit Limit in Selected History Cohort NTD",
}

SCENARIOS = {
    "Baseline": {},
    "September": {"months": ["2005-09"]},
    "September / 2+ months delay": {"months": ["2005-09"], "status": "2+ months delay"},
    "September / 2+ delay / below 50k": {"months": ["2005-09"], "status": "2+ months delay", "credit": "Below 50k"},
    "Aug-Sep / 2+ months delay": {"months": ["2005-08", "2005-09"], "status": "2+ months delay"},
}


def prepare_query():
    rows = []
    for scenario, filters in SCENARIOS.items():
        fields = [f'"Scenario", "{scenario}"'] + [f'"{alias}", [{measure}]' for alias, measure in MEASURES.items()]
        row = "ROW(\n        " + ",\n        ".join(fields) + "\n    )"
        dax_filters = []
        if "months" in filters:
            values = ", ".join(f'"{month}"' for month in filters["months"])
            dax_filters.append("calendar_months[month] IN {" + values + "}")
        if "status" in filters:
            dax_filters.append(f'monthly_repayments[repayment_status_group] = "{filters["status"]}"')
        if "credit" in filters:
            dax_filters.append(f'customers[credit_limit_band] = "{filters["credit"]}"')
        if dax_filters:
            row = "CALCULATETABLE(\n    " + row + ",\n    " + ",\n    ".join(dax_filters) + "\n)"
        rows.append(row)
    QUERY.write_text("// All 18 measures, evaluated by the actual Power BI model.\nEVALUATE\nUNION(\n" + ",\n".join(rows) + "\n)\n", encoding="utf-8")
    print(f"Prepared {len(MEASURES)} measures across {len(SCENARIOS)} scenarios: {QUERY}")


def expected_values(tables, filters):
    customers = tables["customers"]
    customer_ids = None
    if "credit" in filters:
        customer_ids = customers.loc[customers.credit_limit_band.eq(filters["credit"]), "customer_id"]
    expected = reference_metrics(tables, customer_ids=customer_ids, months=filters.get("months"),
                                 status_groups=[filters["status"]] if "status" in filters else None)
    monthly = tables["monthly_repayments"]
    if customer_ids is not None:
        monthly = monthly.loc[monthly.customer_id.isin(customer_ids)]
    if "months" in filters:
        monthly = monthly.loc[monthly.month.isin(filters["months"])]
    if "status" in filters:
        monthly = monthly.loc[monthly.repayment_status_group.eq(filters["status"])]
    expected["negative_bill_rows"] = int(monthly.bill_amount_ntd.lt(0).sum())
    expected["cohort_credit_limit_ntd"] = int(customers.loc[customers.customer_id.isin(monthly.customer_id), "credit_limit_ntd"].sum())
    for prefix in ("documented_delay", "undocumented_status"):
        expected[prefix + "_share"] = expected[prefix + "_rows"] / len(monthly) if len(monthly) else None
    # COUNTROWS of an empty filtered table yields DAX BLANK, not numeric zero.
    # DIVIDE propagates a blank numerator, even with a non-empty denominator.
    for alias in ("documented_delay_rows", "undocumented_status_rows", "negative_bill_rows"):
        if expected[alias] == 0:
            expected[alias] = None
            share = alias.replace("_rows", "_share")
            if share in expected:
                expected[share] = None
    return {alias: expected[alias] for alias in MEASURES}


def run():
    paths = [PROJECT_ROOT / "data" / "exports" / f"{table}.csv"
             for table in ("customers", "monthly_repayments", "default_outcomes", "calendar_months")]
    tables = {path.stem: pd.read_csv(path) for path in paths}
    actual = json.loads(RESULTS.read_text(encoding="utf-8"))
    report = {"status": "failed", "validated_at_utc": datetime.now(timezone.utc).isoformat(),
              "engine": actual["engine"], "queried_at_utc": actual["queried_at_utc"],
              "method": "Actual ADOMD.NET DAX results compared with independent Pandas calculations from validated exports.",
              "measures": MEASURES, "checks": [], "scenarios": {},
              "scope": "DAX runtime validation only; report layout, interactions and saved PBIX require separate Desktop checks."}
    seen = set()
    for raw_row in actual["rows"]:
        row = {key.strip("[]"): value for key, value in raw_row.items()}
        scenario = row.pop("Scenario")
        if scenario not in SCENARIOS or scenario in seen:
            raise ValueError(f"Unexpected or duplicated scenario: {scenario}")
        seen.add(scenario)
        expected = expected_values(tables, SCENARIOS[scenario])
        report["scenarios"][scenario] = row
        for alias, target in expected.items():
            value = row[alias]
            passed = value is None if target is None else value is not None and math.isclose(value, target, rel_tol=1e-12, abs_tol=1e-12)
            report["checks"].append({"scenario": scenario, "measure": MEASURES[alias], "actual": value, "expected": target, "passed": passed})
    if seen != set(SCENARIOS):
        raise ValueError("The runtime result does not contain every required scenario")
    paths += [QUERY, RESULTS, PROJECT_ROOT / "powerbi" / "measures.dax"]
    report["file_sha256"] = {path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    failed = [check for check in report["checks"] if not check["passed"]]
    if not failed:
        report["status"] = "passed"
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failed:
        raise ValueError(f"{len(failed)} DAX checks failed; inspect {REPORT}")
    print(f"Passed {len(report['checks'])} actual DAX checks: {len(MEASURES)} measures, {len(SCENARIOS)} filter scenarios.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Write the readable DAX query without querying Desktop")
    args = parser.parse_args()
    prepare_query() if args.prepare else run()
