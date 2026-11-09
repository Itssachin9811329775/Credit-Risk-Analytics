"""Shared, validated data access and customer-level history features.

All history features use April-September 2005 only. The next-month target is
joined at the end and must be explicitly excluded from any model predictors.
"""

import pandas as pd

from .build_database import (
    DATABASE_PATH, TABLE_KEYS, connect_database, load_verified_clean,
    make_tables, validate_database,
)
from .download_data import sha256


STATUS_GROUPS = ["Undocumented -2", "Paid duly (-1)", "Undocumented 0", "1 month delay", "2+ months delay"]
CREDIT_BANDS = ["Below 50k", "50k-<100k", "100k-<200k", "200k+"]
AGE_BANDS = ["Under 30", "30-39", "40-49", "50+"]


def status_group(code):
    """Do not interpret undocumented codes as either paid-duly or delayed."""
    if code == -2:
        return "Undocumented -2"
    if code == -1:
        return "Paid duly (-1)"
    if code == 0:
        return "Undocumented 0"
    if code == 1:
        return "1 month delay"
    if 2 <= code <= 9:
        return "2+ months delay"
    raise ValueError(f"Unrecognised repayment code: {code}")


def make_customer_features(customers, monthly, outcomes):
    """Aggregate first, then validate every merge as one-to-one."""
    if monthly.duplicated(["customer_id", "month"]).any():
        raise ValueError("Duplicate customer-month records cannot become customer features.")
    observations = monthly.assign(
        delayed=monthly.repayment_status.ge(1).astype(int),
        severe_delay=monthly.repayment_status.ge(2).astype(int),
        unknown_status=monthly.repayment_status.isin([-2, 0]).astype(int),
        paid_duly=monthly.repayment_status.eq(-1).astype(int),
        zero_payment=monthly.payment_amount_ntd.eq(0).astype(int),
    )
    history = observations.groupby("customer_id", as_index=False).agg(
        history_months=("month", "nunique"),
        delayed_months=("delayed", "sum"),
        severe_delay_months=("severe_delay", "sum"),
        unknown_status_months=("unknown_status", "sum"),
        paid_duly_months=("paid_duly", "sum"),
        zero_payment_months=("zero_payment", "sum"),
        total_payment_ntd=("payment_amount_ntd", "sum"),
    )
    if not history.history_months.eq(6).all():
        raise ValueError("Every customer must have six distinct history months.")
    latest = monthly.loc[monthly.month.eq("2005-09"), [
        "customer_id", "repayment_status", "bill_amount_ntd", "payment_amount_ntd",
    ]].rename(columns={
        "repayment_status": "latest_repayment_status",
        "bill_amount_ntd": "latest_bill_amount_ntd",
        "payment_amount_ntd": "latest_payment_amount_ntd",
    })
    features = customers.merge(history, on="customer_id", how="left", validate="one_to_one")
    features = features.merge(latest, on="customer_id", how="left", validate="one_to_one")
    features = features.merge(outcomes, on="customer_id", how="left", validate="one_to_one")
    if len(features) != len(customers) or features.isna().any().any():
        raise ValueError("Feature joins changed customer coverage or created missing values.")
    if not (features.delayed_months + features.unknown_status_months + features.paid_duly_months).eq(6).all():
        raise ValueError("Repayment states do not partition the six history months.")
    features["latest_status_group"] = features.latest_repayment_status.map(status_group)
    features["latest_bill_to_limit"] = features.latest_bill_amount_ntd / features.credit_limit_ntd
    # Bands are descriptive choices fixed before inspecting the default target.
    features["credit_limit_band"] = pd.cut(features.credit_limit_ntd, [0, 50_000, 100_000, 200_000, float("inf")],
                                           labels=CREDIT_BANDS, right=False).astype(str)
    features["age_band"] = pd.cut(features.age, [0, 30, 40, 50, float("inf")], labels=AGE_BANDS, right=False).astype(str)
    return features.sort_values("customer_id").reset_index(drop=True)


def load_analysis_data():
    """Read the real database and verify its schema, contents, and upstream source.

    Return four DataFrames plus a serializable provenance dictionary. This does
    not rewrite the database or earlier reports and needs no network connection.
    """
    validation = {"checks": []}
    clean = load_verified_clean(validation)
    expected = make_tables(clean)
    connection = connect_database(DATABASE_PATH, readonly=True)
    try:
        validate_database(connection, expected, validation)
        data = {name: pd.read_sql_query(f"SELECT * FROM {name} ORDER BY {', '.join(keys)}", connection)
                for name, keys in TABLE_KEYS.items()}
    finally:
        connection.close()
    data["customer_features"] = make_customer_features(data["customers"], data["monthly_repayments"], data["default_outcomes"])
    data["provenance"] = {
        "database_sha256": sha256(DATABASE_PATH.read_bytes()),
        "clean_csv_sha256": validation["input"]["clean_csv_sha256"],
        "source": validation["input"]["source"],
        "validation_checks_passed": len(validation["checks"]),
        "customer_count": len(data["customers"]),
        "history_start": "2005-04", "history_end": "2005-09",
    }
    return data
