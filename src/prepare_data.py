r"""Stage 2: validate the real UCI workbook and create an auditable customer CSV.

Run from the project root: .\.venv\Scripts\python.exe -m src.prepare_data
Use --offline after the first download to verify and reuse the original files.
"""

import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .download_data import MANIFEST_PATH, PROJECT_ROOT, ensure_dataset, sha256


PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "reports"
TARGET = "default payment next month"
# Suffix 1 is September for bills/payments, but repayment status uses PAY_0.
MONTHS = [
    ("2005-04", "PAY_6", "BILL_AMT6", "PAY_AMT6"),
    ("2005-05", "PAY_5", "BILL_AMT5", "PAY_AMT5"),
    ("2005-06", "PAY_4", "BILL_AMT4", "PAY_AMT4"),
    ("2005-07", "PAY_3", "BILL_AMT3", "PAY_AMT3"),
    ("2005-08", "PAY_2", "BILL_AMT2", "PAY_AMT2"),
    ("2005-09", "PAY_0", "BILL_AMT1", "PAY_AMT1"),
]
STATUS_COLUMNS = [row[1] for row in MONTHS]
BILL_COLUMNS = [row[2] for row in MONTHS]
PAYMENT_COLUMNS = [row[3] for row in MONTHS]
EXPECTED_COLUMNS = (
    ["ID", "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE"]
    + list(reversed(STATUS_COLUMNS))
    + list(reversed(BILL_COLUMNS))
    + list(reversed(PAYMENT_COLUMNS))
    + [TARGET]
)
CATEGORY_LABELS = {
    "SEX": {1: "Male", 2: "Female"},
    "EDUCATION": {1: "Graduate school", 2: "University", 3: "High school", 4: "Other"},
    "MARRIAGE": {1: "Married", 2: "Single", 3: "Other"},
}
DOCUMENTED_STATUS_CODES = {-1, *range(1, 10)}
ACCEPTED_STATUS_CODES = DOCUMENTED_STATUS_CODES | {-2, 0}


def check(report, name, condition, detail):
    """Fail explicitly; unlike assert, this remains active with python -O."""
    passed = bool(condition)
    report["checks"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        raise ValueError(f"{name}: {detail}")


def validate_raw(raw, report):
    """Check structural and numeric integrity before any cleaning or export."""
    check(report, "Expected schema", list(raw.columns) == EXPECTED_COLUMNS,
          "Exactly the 25 expected source columns in their original order")
    check(report, "Expected row count", len(raw) == 30_000, f"Observed {len(raw):,}; expected 30,000")
    check(report, "No missing values", not raw.isna().any().any(), f"Missing cells: {int(raw.isna().sum().sum())}")
    numeric = all(pd.api.types.is_numeric_dtype(dtype) for dtype in raw.dtypes)
    check(report, "Numeric source fields", numeric, "Every source field must be numeric")
    values = raw.to_numpy(dtype="float64")
    safe_integers = (
        np.isfinite(values).all()
        and (values == np.floor(values)).all()
        and ((values >= -(2**63)) & (values < 2**63)).all()
    )
    check(report, "Finite integer values", safe_integers,
          "Finite whole numbers safely convertible to int64; no fractions or overflowing values")
    check(report, "Unique positive customer IDs", raw["ID"].is_unique and raw["ID"].gt(0).all(),
          f"Repeated IDs: {int(raw['ID'].duplicated().sum())}")
    check(report, "Binary target", raw[TARGET].isin([0, 1]).all(), "Target codes must be 0 or 1")
    check(report, "Positive credit limits", raw["LIMIT_BAL"].gt(0).all(), "Credit limits must exceed zero")
    check(report, "Plausible age", raw["AGE"].between(18, 100).all(),
          "Project investigation guardrail: ages 18-100 inclusive; not a UCI eligibility rule")
    check(report, "Recognised sex codes", raw["SEX"].isin([1, 2]).all(), "Codes 1 and 2 as documented")
    check(report, "Education codes inspected", raw["EDUCATION"].isin(range(7)).all(),
          "Observed codes 0-6 accepted; 0, 5, 6 will be labelled undocumented")
    check(report, "Marriage codes inspected", raw["MARRIAGE"].isin(range(4)).all(),
          "Codes 0-3 accepted; 0 will be labelled undocumented")
    check(report, "Repayment codes inspected", raw[STATUS_COLUMNS].isin(ACCEPTED_STATUS_CODES).all().all(),
          "Documented -1 and 1-9, plus observed undocumented -2 and 0")
    check(report, "Nonnegative payment amounts", raw[PAYMENT_COLUMNS].ge(0).all().all(),
          "Negative payments require investigation; negative bills are retained")


def column_mapping():
    mapping = {
        "ID": "customer_id", "LIMIT_BAL": "credit_limit_ntd", "SEX": "sex_code",
        "EDUCATION": "education_code", "MARRIAGE": "marriage_code", "AGE": "age",
        TARGET: "default_next_month",
    }
    for month, status, bill, payment in MONTHS:
        suffix = month.replace("-", "_")
        mapping[status] = f"repayment_status_{suffix}"
        mapping[bill] = f"bill_amount_{suffix}_ntd"
        mapping[payment] = f"payment_amount_{suffix}_ntd"
    return mapping


def clean_data(raw):
    """Keep all records and numeric values; add readable names, labels, and flags."""
    clean = raw.astype("int64").rename(columns=column_mapping())
    for source, clean_prefix in (("SEX", "sex"), ("EDUCATION", "education"), ("MARRIAGE", "marriage")):
        clean[f"{clean_prefix}_label"] = raw[source].map(
            lambda code: CATEGORY_LABELS[source].get(code, f"Undocumented (code {code})")
        )
    clean["has_negative_bill"] = raw[BILL_COLUMNS].lt(0).any(axis=1)
    clean["has_undocumented_repayment_code"] = ~raw[STATUS_COLUMNS].isin(DOCUMENTED_STATUS_CODES).all(axis=1)
    return clean.sort_values("customer_id", kind="stable").reset_index(drop=True)


def inspect_data(raw):
    """Produce observed quality findings, not business conclusions."""
    negative_bills = raw[BILL_COLUMNS].lt(0)
    unknown_status = ~raw[STATUS_COLUMNS].isin(DOCUMENTED_STATUS_CODES)
    return {
        "customer_count": len(raw),
        "source_column_count": len(raw.columns),
        "missing_cells": int(raw.isna().sum().sum()),
        "duplicate_ids": int(raw["ID"].duplicated().sum()),
        "duplicate_full_rows": int(raw.duplicated().sum()),
        "repeated_profiles_excluding_id": int(raw.drop(columns="ID").duplicated().sum()),
        "repeated_predictor_profiles_excluding_id_and_target": int(raw.drop(columns=["ID", TARGET]).duplicated().sum()),
        "undocumented_education_customers": int((~raw["EDUCATION"].isin(CATEGORY_LABELS["EDUCATION"])).sum()),
        "undocumented_marriage_customers": int((~raw["MARRIAGE"].isin(CATEGORY_LABELS["MARRIAGE"])).sum()),
        "undocumented_repayment_cells": int(unknown_status.sum().sum()),
        "customers_with_undocumented_repayment_codes": int(unknown_status.any(axis=1).sum()),
        "negative_bill_cells": int(negative_bills.sum().sum()),
        "customers_with_negative_bills": int(negative_bills.any(axis=1).sum()),
        "negative_payment_cells": int(raw[PAYMENT_COLUMNS].lt(0).sum().sum()),
        "default_customers": int(raw[TARGET].sum()),
        "nondefault_customers": int(raw[TARGET].eq(0).sum()),
        "sample_default_rate": float(raw[TARGET].mean()),
        "minimum_age": int(raw["AGE"].min()),
        "maximum_age": int(raw["AGE"].max()),
        "minimum_credit_limit_ntd": int(raw["LIMIT_BAL"].min()),
        "maximum_credit_limit_ntd": int(raw["LIMIT_BAL"].max()),
    }


def write_reference_files(raw, clean):
    """Save machine-readable inspection details and the six-month mapping."""
    profile = pd.DataFrame({
        "source_column": raw.columns,
        "dtype": raw.dtypes.astype(str).to_numpy(),
        "missing_count": raw.isna().sum().to_numpy(),
        "distinct_count": raw.nunique().to_numpy(),
        "minimum": raw.min().to_numpy(),
        "maximum": raw.max().to_numpy(),
        "zero_count": raw.eq(0).sum().to_numpy(),
        "negative_count": raw.lt(0).sum().to_numpy(),
    })
    profile.to_csv(REPORT_DIR / "column_profile.csv", index=False)

    category_rows = []
    for column in [*CATEGORY_LABELS, *STATUS_COLUMNS, TARGET]:
        if column in CATEGORY_LABELS:
            documented = set(CATEGORY_LABELS[column])
        else:
            documented = {0, 1} if column == TARGET else DOCUMENTED_STATUS_CODES
        for code, count in raw[column].value_counts().sort_index().items():
            category_rows.append({"source_column": column, "code": code, "count": count,
                                  "documented_in_uci_description": code in documented})
    pd.DataFrame(category_rows).to_csv(REPORT_DIR / "category_counts.csv", index=False)

    rename = column_mapping()
    month_rows = [{"month": month, "source_status": status, "source_bill": bill, "source_payment": payment,
                   "clean_status": rename[status], "clean_bill": rename[bill], "clean_payment": rename[payment]}
                  for month, status, bill, payment in MONTHS]
    pd.DataFrame(month_rows).to_csv(PROCESSED_DIR / "month_mapping.csv", index=False)

    descriptions = {
        "ID": ("identifier", "Customer key; one row per customer"),
        "LIMIT_BAL": ("NTD", "Given credit amount; retained exactly"),
        "SEX": ("category code", "1 Male; 2 Female; source labels"),
        "EDUCATION": ("category code", "1 Graduate school; 2 University; 3 High school; 4 Other; 0/5/6 undocumented"),
        "MARRIAGE": ("category code", "1 Married; 2 Single; 3 Other; 0 undocumented"),
        "AGE": ("years", "Age as provided"),
        TARGET: ("binary outcome", "Next-month default: 1 Yes; 0 No. One outcome per customer; never a predictor"),
    }
    for month, status, bill, payment in MONTHS:
        descriptions[status] = ("repayment code", f"{month}: -1 paid duly; 1-8 months of delay; 9 nine or more; -2/0 undocumented")
        descriptions[bill] = ("NTD", f"{month} bill statement amount; negative values retained")
        descriptions[payment] = ("NTD", f"Amount of previous payment recorded for {month}; not a contractual recovery rate")
    dictionary = [{"column": rename[column], "source_column": column, "dtype": str(clean[rename[column]].dtype),
                   "unit": descriptions[column][0], "definition": descriptions[column][1]}
                  for column in raw.columns]
    for name in ("sex", "education", "marriage"):
        dictionary.append({"column": f"{name}_label", "source_column": f"derived from {name}_code",
                           "dtype": "object", "unit": "label", "definition": "Documented source label or explicit undocumented code"})
    dictionary.extend([
        {"column": "has_negative_bill", "source_column": "derived from BILL_AMT1-6", "dtype": "bool", "unit": "flag",
         "definition": "At least one bill amount is below zero; its cause is unknown"},
        {"column": "has_undocumented_repayment_code", "source_column": "derived from PAY_0, PAY_2-6", "dtype": "bool", "unit": "flag",
         "definition": "At least one repayment code is -2 or 0; do not label these as on-time"},
    ])
    pd.DataFrame(dictionary).to_csv(PROCESSED_DIR / "data_dictionary.csv", index=False)


def write_summary(report):
    facts = report["observations"]
    text = f"""# Stage 2: observed data quality

Generated by `python -m src.prepare_data` from the preserved UCI 350 workbook.
Run timestamp (UTC): {report['run_at_utc']}. Status: **{report['status']}**.

- Customers: {facts['customer_count']:,}; source columns: {facts['source_column_count']}.
- Clean output: {report['clean_shape'][0]:,} rows and {report['clean_shape'][1]} columns, one row per customer.
- Missing cells: {facts['missing_cells']}; duplicate customer IDs: {facts['duplicate_ids']}.
- Next-month defaults: {facts['default_customers']:,} of {facts['customer_count']:,} customers ({facts['sample_default_rate']:.2%}).
- Undocumented education codes: {facts['undocumented_education_customers']:,} customers; undocumented marriage codes: {facts['undocumented_marriage_customers']:,}.
- Undocumented repayment codes: {facts['undocumented_repayment_cells']:,} cells across six months, affecting {facts['customers_with_undocumented_repayment_codes']:,} customers.
- Negative bill amounts: {facts['negative_bill_cells']:,} cells, affecting {facts['customers_with_negative_bills']:,} customers; negative payment amounts: {facts['negative_payment_cells']}.
- Repeated rows after excluding ID: {facts['repeated_profiles_excluding_id']}; after excluding both ID and target: {facts['repeated_predictor_profiles_excluding_id_and_target']} (counts after the first occurrence in each group).
- Age range: {facts['minimum_age']}-{facts['maximum_age']} years. Credit-limit range: {facts['minimum_credit_limit_ntd']:,}-{facts['maximum_credit_limit_ntd']:,} NTD.
- Validation checks passed: {len(report['checks'])}.

## Cleaning decisions

All customers and all 25 original numeric values per customer are retained.
Columns are renamed, codes receive readable labels where supported, and two
quality flags are added. No imputation, deduplication, clipping, scaling, or
removal of outliers is performed. Negative bills have no proven explanation in
this file. Distinct customer IDs are retained even when profiles match.

Repayment codes -2 and 0 are kept as undocumented; they are not converted to
delinquency, on-time, or months-overdue values. Known paid-duly code -1 and delay
codes 1-9 remain distinct. The default target is a single future outcome per
customer, not six monthly outcomes.

The default percentage is descriptive for this sample. It is not a model score,
a causal finding, or an estimate of Finnable's portfolio. No collections-action
effectiveness can be measured from this file. See `docs/data_source.md` for
attribution and `docs/stage_02_data_preparation.md` for the workflow.
"""
    (REPORT_DIR / "stage_02_summary.md").write_text(text, encoding="utf-8")


def run(offline=False):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report = {"stage": 2, "status": "failed", "run_at_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    try:
        workbook = ensure_dataset(offline=offline)
        report["source"] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        with pd.ExcelFile(workbook, engine="xlrd") as excel:
            report["sheet_names"] = excel.sheet_names
            check(report, "Expected workbook sheet", excel.sheet_names == ["Data"], "Expected the inspected Data sheet")
            raw = pd.read_excel(excel, sheet_name="Data", header=1)
        report["parsing"] = {"sheet": "Data", "header_excel_row": 2, "engine": "xlrd"}
        report["raw_shape"] = list(raw.shape)
        validate_raw(raw, report)
        report["observations"] = inspect_data(raw)
        clean = clean_data(raw)
        report["clean_shape"] = list(clean.shape)
        check(report, "All customers retained", len(clean) == len(raw) and set(clean.customer_id) == set(raw.ID),
              "No source customer added or removed")
        check(report, "Clean key unique and complete", clean.customer_id.is_unique and clean.customer_id.notna().all(),
              "Exactly one row per customer")
        original_sorted = raw.astype("int64").sort_values("ID").reset_index(drop=True)
        retained = clean[list(column_mapping()[column] for column in raw.columns)].copy()
        retained.columns = raw.columns
        check(report, "Source values preserved", retained.equals(original_sorted),
              "Every original numeric value, including unknown codes and negative bills, matches")
        check(report, "No missing cleaned values", not clean.isna().any().any(), "Labels and flags are populated")

        output = PROCESSED_DIR / "credit_clients_clean.csv"
        temporary = output.with_suffix(".csv.tmp")
        clean.to_csv(temporary, index=False, encoding="utf-8")
        reread = pd.read_csv(temporary)
        check(report, "CSV round-trip matches", clean.equals(reread), "Values, dtypes, columns, and rows survive CSV export")
        temporary.replace(output)
        write_reference_files(raw, clean)
        report["clean_file"] = {"path": output.relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256(output.read_bytes())}
        report["status"] = "passed"
        write_summary(report)
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        (REPORT_DIR / "stage_02_summary.md").write_text(
            "# Stage 2: validation failed\n\n"
            f"Run timestamp (UTC): {report['run_at_utc']}.\n\n"
            "See `reports/data_quality.json` for the failure. Any existing CSVs may\n"
            "belong to a previous run; do not use them until validation passes.\n",
            encoding="utf-8",
        )
        raise
    finally:
        (REPORT_DIR / "data_quality.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    facts = report["observations"]
    print(f"Stage 2 passed: {len(report['checks'])} checks; {len(clean):,} customers; {len(clean.columns)} clean columns.")
    print(f"Sample next-month default rate: {facts['default_customers']:,}/{len(clean):,} = {facts['sample_default_rate']:.2%}")
    print(f"Clean CSV: {output}")
    print(f"Quality summary: {REPORT_DIR / 'stage_02_summary.md'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require an existing download; never access the network")
    arguments = parser.parse_args()
    run(offline=arguments.offline)
