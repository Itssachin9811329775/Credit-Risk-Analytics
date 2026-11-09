r"""Stage 3: create and validate the SQLite database from the verified clean CSV.

Build: .\.venv\Scripts\python.exe -m src.build_database
Check existing DB without rebuilding: add --validate-only.
"""

import argparse
import io
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .download_data import PROJECT_ROOT, sha256, verify_cached_download
from .prepare_data import EXPECTED_COLUMNS, MONTHS, check, column_mapping


DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "credit_risk.sqlite"
REPORT_DIR = PROJECT_ROOT / "reports"
CLEAN_PATH = PROJECT_ROOT / "data" / "processed" / "credit_clients_clean.csv"
QUALITY_PATH = REPORT_DIR / "data_quality.json"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
JOIN_CHECK_PATH = PROJECT_ROOT / "sql" / "check_join_grain.sql"
APPLICATION_ID = 0x43524131  # 'CRA1': identifies this generated project database.
CUSTOMER_COLUMNS = [
    "customer_id", "credit_limit_ntd", "sex_code", "education_code", "marriage_code", "age",
    "sex_label", "education_label", "marriage_label", "has_negative_bill", "has_undocumented_repayment_code",
]
TABLE_KEYS = {
    "customers": ["customer_id"],
    "monthly_repayments": ["customer_id", "month"],
    "default_outcomes": ["customer_id"],
}


def connect_database(path, readonly=False):
    """Set foreign-key enforcement on EACH connection, before any transaction."""
    uri = Path(path).resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw")
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def load_verified_clean(report, clean_path=CLEAN_PATH, quality_path=QUALITY_PATH):
    """Read the exact bytes validated in stage 2; no downloads or silent repair."""
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    check(report, "Stage 2 passed", quality.get("stage") == 2 and quality.get("status") == "passed"
          and bool(quality.get("checks")) and all(item["passed"] for item in quality["checks"]),
          "Run src.prepare_data successfully before building the database")
    manifest = verify_cached_download()
    check(report, "Source provenance matches", quality.get("source") == manifest,
          "Preserved original files and stage-2 source metadata agree")
    content = clean_path.read_bytes()
    digest = sha256(content)
    check(report, "Clean CSV checksum matches", digest == quality["clean_file"]["sha256"],
          "No manual changes to the CSV since stage-2 validation")
    clean = pd.read_csv(io.BytesIO(content))
    expected_columns = [column_mapping()[name] for name in EXPECTED_COLUMNS] + [
        "sex_label", "education_label", "marriage_label", "has_negative_bill", "has_undocumented_repayment_code",
    ]
    check(report, "Clean schema and shape", list(clean.columns) == expected_columns
          and list(clean.shape) == quality["clean_shape"] and len(clean) == 30_000,
          f"Observed {len(clean):,} customers and {len(clean.columns)} columns")
    check(report, "Clean customer key", clean.customer_id.is_unique and clean.customer_id.notna().all(),
          "Input contains exactly one nonmissing row per customer")
    report["input"] = {"clean_csv_sha256": digest, "stage_2_run_at_utc": quality["run_at_utc"],
                       "source": manifest}
    return clean


def make_tables(clean):
    """Reshape six explicitly mapped columns into six rows per customer."""
    customers = clean[CUSTOMER_COLUMNS].copy()
    for flag in ("has_negative_bill", "has_undocumented_repayment_code"):
        customers[flag] = customers[flag].astype("int64")  # SQLite stores flags as 0/1.
    pieces = []
    for month, _, _, _ in MONTHS:
        suffix = month.replace("-", "_")
        part = clean[["customer_id", f"repayment_status_{suffix}",
                      f"bill_amount_{suffix}_ntd", f"payment_amount_{suffix}_ntd"]].copy()
        part.columns = ["customer_id", "repayment_status", "bill_amount_ntd", "payment_amount_ntd"]
        part.insert(1, "month", month)
        pieces.append(part)
    tables = {
        "customers": customers,
        "monthly_repayments": pd.concat(pieces, ignore_index=True),
        "default_outcomes": clean[["customer_id", "default_next_month"]].copy(),
    }
    return {name: frame.sort_values(TABLE_KEYS[name]).reset_index(drop=True) for name, frame in tables.items()}


def insert_tables(connection, tables):
    """Use explicit schema + bound values; do not let to_sql replace constraints."""
    for name, frame in tables.items():
        # Identifiers come only from the internal table definitions, never user input.
        columns = ", ".join(frame.columns)
        placeholders = ", ".join("?" for _ in frame.columns)
        connection.executemany(f"INSERT INTO {name} ({columns}) VALUES ({placeholders})",
                               frame.itertuples(index=False, name=None))


def query_records(connection, sql):
    cursor = connection.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def validate_database(connection, tables, report):
    """Reconcile actual stored values, coverage, and safe/unsafe join grains."""
    check(report, "Foreign keys enabled", connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1,
          "Enforcement enabled for this connection")
    check(report, "Project database identity", connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
          and connection.execute("PRAGMA user_version").fetchone()[0] == 1, "Generated project database, schema version 1")
    actual_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    check(report, "Expected tables", actual_names == set(TABLE_KEYS), "Exactly customers, monthly_repayments, default_outcomes")
    # foreign_key_check alone cannot detect a missing FK declaration. Compare
    # the installed tables/constraints/index to a fresh copy of our schema.
    schema_query = "SELECT type, name, tbl_name, sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    expected_schema = sqlite3.connect(":memory:")
    try:
        expected_schema.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_matches = connection.execute(schema_query).fetchall() == expected_schema.execute(schema_query).fetchall()
    finally:
        expected_schema.close()
    check(report, "Installed schema matches", schema_matches,
          "Table definitions, foreign keys, CHECK constraints, and index match sql/schema.sql")
    options = {row[1]: (row[4], row[5]) for row in connection.execute("PRAGMA table_list") if row[1] in TABLE_KEYS}
    check(report, "Strict tables with explicit keys", all(value == (1, 1) for value in options.values()),
          "All three tables use STRICT and WITHOUT ROWID")
    check(report, "SQLite integrity", connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
          "SQLite reports no structural or CHECK-constraint errors")
    check(report, "No foreign-key violations", not connection.execute("PRAGMA foreign_key_check").fetchall(),
          "No repayment or outcome references an absent customer")

    report["row_counts"] = {}
    for name, expected in tables.items():
        order = ", ".join(TABLE_KEYS[name])
        stored = pd.read_sql_query(f"SELECT * FROM {name} ORDER BY {order}", connection)
        report["row_counts"][name] = len(stored)
        check(report, f"{name}: row count", len(stored) == len(expected), f"{len(stored):,} rows")
        check(report, f"{name}: every value matches", stored.equals(expected),
              "All keys, columns, labels, flags, codes, and amounts reconcile to the source")
        key_columns = [row[1] for row in sorted(connection.execute(f"PRAGMA table_info({name})").fetchall(), key=lambda row: row[5]) if row[5]]
        check(report, f"{name}: primary key", key_columns == TABLE_KEYS[name], ", ".join(TABLE_KEYS[name]))

    coverage_errors = connection.execute("""
        SELECT c.customer_id
        FROM customers AS c
        LEFT JOIN monthly_repayments AS m ON m.customer_id = c.customer_id
        GROUP BY c.customer_id
        HAVING COUNT(m.month) != 6 OR COUNT(DISTINCT m.month) != 6
    """).fetchall()
    check(report, "Six months for every customer", not coverage_errors, f"Customers with incomplete/duplicate history: {len(coverage_errors)}")
    missing_outcomes = connection.execute("""
        SELECT COUNT(*) FROM customers AS c
        LEFT JOIN default_outcomes AS d ON d.customer_id = c.customer_id
        WHERE d.customer_id IS NULL
    """).fetchone()[0]
    check(report, "Outcome for every customer", missing_outcomes == 0, f"Customers without an outcome: {missing_outcomes}")

    monthly = query_records(connection, """
        SELECT month, COUNT(*) AS customer_month_rows,
               SUM(bill_amount_ntd) AS bill_amount_sum_ntd,
               SUM(payment_amount_ntd) AS payment_amount_sum_ntd,
               SUM(CASE WHEN bill_amount_ntd < 0 THEN 1 ELSE 0 END) AS negative_bill_rows,
               SUM(CASE WHEN repayment_status IN (-2, 0) THEN 1 ELSE 0 END) AS undocumented_status_rows
        FROM monthly_repayments GROUP BY month ORDER BY month
    """)
    check(report, "Six expected calendar months", [row["month"] for row in monthly] == [row[0] for row in MONTHS],
          "April to September 2005, in order")
    check(report, "Each month covers all customers", all(row["customer_month_rows"] == len(tables["customers"]) for row in monthly),
          "Each monthly denominator is 30,000 customers")
    report["monthly_reconciliation"] = monthly

    joins = query_records(connection, JOIN_CHECK_PATH.read_text(encoding="utf-8"))
    report["join_grain_checks"] = joins
    baseline = {
        "row_count": len(tables["customers"]), "unique_customers": len(tables["customers"]),
        "credit_limit_sum_ntd": int(tables["customers"].credit_limit_ntd.sum()),
        "default_count": int(tables["default_outcomes"].default_next_month.sum()),
    }
    for row in joins:
        expected = baseline.copy()
        if row["join_pattern"] == "direct_monthly_join":
            for name in ("row_count", "credit_limit_sum_ntd", "default_count"):
                expected[name] *= len(MONTHS)
        check(report, f"Join grain: {row['join_pattern']}", all(row[key] == value for key, value in expected.items()),
              "Sixfold duplication demonstrated" if row["join_pattern"] == "direct_monthly_join" else "Customer-level counts and sums preserved")
    report["customer_totals"] = baseline
    report["sample_default_rate"] = baseline["default_count"] / baseline["row_count"]


def write_summary(report):
    totals = report["customer_totals"]
    text = f"""# Stage 3: SQLite validation

Generated by `python -m src.build_database`. Status: **passed**.
Mode: {report['mode']}. Run timestamp (UTC): {report['run_at_utc']}.

- `customers`: {report['row_counts']['customers']:,} rows; one per customer.
- `monthly_repayments`: {report['row_counts']['monthly_repayments']:,} rows; one per customer per month.
- `default_outcomes`: {report['row_counts']['default_outcomes']:,} rows; one future outcome per customer.
- All {len(report['checks'])} validation checks passed; all stored values match the verified clean source.
- Every customer has all six months and exactly one outcome. No orphaned references were found.
- Customer-level defaults: {totals['default_count']:,} / {totals['row_count']:,} = {report['sample_default_rate']:.2%}.
- Sum of customer credit limits: {totals['credit_limit_sum_ntd']:,} NTD (not outstanding debt).

## Why join grain matters

Joining customers directly to six monthly records produces {totals['row_count'] * 6:,}
rows and repeats each customer's credit limit and default flag six times.
Summing those repeated default flags produces {totals['default_count'] * 6:,},
which is not a count of defaulting customers. Aggregating monthly records to one
row per customer before joining preserves the correct totals.

`COUNT(DISTINCT customer_id)` fixes the customer count alone, not duplicated sums.
The default percentage happens to survive an unfiltered six-row-per-customer
join; this does not validate the counts or protect against uneven row coverage.

The detailed JSON includes all checks, month-level reconciliations, three join
examples, source provenance, input/schema hashes, and the database checksum.
This is the historical UCI sample, not Finnable data. No causal effects or
collections improvements are inferred. Stage 4 business analyses are next.
"""
    (REPORT_DIR / "stage_03_summary.md").write_text(text, encoding="utf-8")


def run(validate_only=False):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"stage": 3, "status": "failed", "mode": "validate_only" if validate_only else "build",
              "run_at_utc": datetime.now(timezone.utc).isoformat(), "sqlite_version": sqlite3.sqlite_version, "checks": []}
    candidate = None
    try:
        check(report, "SQLite supports STRICT", sqlite3.sqlite_version_info >= (3, 37, 0), sqlite3.sqlite_version)
        clean = load_verified_clean(report)
        tables = make_tables(clean)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        report["schema_sha256"] = sha256(SCHEMA_PATH.read_bytes())
        if validate_only:
            connection = connect_database(DATABASE_PATH, readonly=True)
            try:
                validate_database(connection, tables, report)
            finally:
                connection.close()
        else:
            DATABASE_DIR.mkdir(parents=True, exist_ok=True)
            if DATABASE_PATH.exists():
                previous = connect_database(DATABASE_PATH, readonly=True)
                try:
                    if previous.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                        raise ValueError("Existing database is not this project's generated artifact; it will not be replaced.")
                    previous_tables = {row[0] for row in previous.execute("SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
                    if previous_tables != set(TABLE_KEYS):
                        raise ValueError("Existing database has unexpected tables; inspect it before rebuilding.")
                finally:
                    previous.close()
            # A separate candidate protects the current database if loading fails.
            with tempfile.NamedTemporaryFile(prefix="credit_risk_build_", suffix=".sqlite", dir=DATABASE_DIR, delete=False) as temporary:
                candidate = Path(temporary.name)
            connection = connect_database(candidate)
            try:
                connection.executescript(schema)
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute("PRAGMA user_version = 1")
                with connection:  # Commit all inserts together; rollback on error.
                    insert_tables(connection, tables)
                    validate_database(connection, tables, report)
            finally:
                connection.close()
            candidate.replace(DATABASE_PATH)  # Connections are closed before Windows replacement.
            candidate = None
        report["database"] = {"path": DATABASE_PATH.relative_to(PROJECT_ROOT).as_posix(),
                              "sha256": sha256(DATABASE_PATH.read_bytes()), "size_bytes": DATABASE_PATH.stat().st_size}
        report["status"] = "passed"
        write_summary(report)
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        (REPORT_DIR / "stage_03_summary.md").write_text(
            "# Stage 3: validation failed\n\nSee `reports/database_validation.json` for the error.\n"
            "An existing database may be from an earlier successful build. Resolve the error\n"
            "and rerun validation before using it for analysis.\n", encoding="utf-8")
        raise
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)  # Only this run's generated temporary file.
        (REPORT_DIR / "database_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Stage 3 passed: {len(report['checks'])} checks.")
    for name, count in report["row_counts"].items():
        print(f"  {name}: {count:,} rows")
    print(f"Database: {DATABASE_PATH}")
    print(f"Validation summary: {REPORT_DIR / 'stage_03_summary.md'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Validate the existing database using a read-only connection")
    arguments = parser.parse_args()
    run(validate_only=arguments.validate_only)
