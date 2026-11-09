"""Check SQLite safeguards using the real UCI data in memory or temporary files.

Deliberately invalid changes are test inputs only. The project's database,
source files, cleaned CSV, and reports are never modified by these tests.
"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import build_database as database
from src.download_data import WORKBOOK_PATH


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not database.CLEAN_PATH.exists() or not database.QUALITY_PATH.exists():
            raise unittest.SkipTest("Run stage 2 before these offline database tests.")
        cls.clean = database.load_verified_clean({"checks": []})
        cls.tables = database.make_tables(cls.clean)
        cls.connection = sqlite3.connect(":memory:")
        cls.connection.executescript(database.SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.connection.execute(f"PRAGMA application_id = {database.APPLICATION_ID}")
        cls.connection.execute("PRAGMA user_version = 1")
        database.insert_tables(cls.connection, cls.tables)
        cls.connection.commit()

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def tearDown(self):
        self.connection.rollback()  # Restore the shared in-memory source after each test.

    def test_real_database_reconciles(self):
        report = {"checks": []}
        database.validate_database(self.connection, self.tables, report)
        self.assertTrue(all(item["passed"] for item in report["checks"]))
        self.assertEqual(report["row_counts"]["monthly_repayments"], len(self.clean) * 6)

    def test_endpoint_months_match_original_workbook_columns(self):
        # Independent source mapping protects against a shared reshape/validator bug.
        raw = pd.read_excel(WORKBOOK_PATH, sheet_name="Data", header=1, engine="xlrd")
        for month, sources in (("2005-09", ["PAY_0", "BILL_AMT1", "PAY_AMT1"]),
                               ("2005-04", ["PAY_6", "BILL_AMT6", "PAY_AMT6"])):
            with self.subTest(month=month):
                expected = raw[["ID", *sources]].sort_values("ID").reset_index(drop=True)
                expected.columns = ["customer_id", "repayment_status", "bill_amount_ntd", "payment_amount_ntd"]
                stored = pd.read_sql_query(
                    "SELECT customer_id, repayment_status, bill_amount_ntd, payment_amount_ntd "
                    "FROM monthly_repayments WHERE month = ? ORDER BY customer_id",
                    self.connection, params=(month,),
                )
                self.assertTrue(stored.equals(expected))

    def test_schema_without_foreign_keys_is_rejected(self):
        schema = database.SCHEMA_PATH.read_text(encoding="utf-8")
        foreign_key = (",\n    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)\n"
                       "        ON UPDATE RESTRICT ON DELETE RESTRICT")
        self.assertEqual(schema.count(foreign_key), 2)
        altered = sqlite3.connect(":memory:")
        try:
            altered.executescript(schema.replace(foreign_key, ""))
            altered.execute(f"PRAGMA application_id = {database.APPLICATION_ID}")
            altered.execute("PRAGMA user_version = 1")
            with self.assertRaisesRegex(ValueError, "Installed schema matches"):
                database.validate_database(altered, self.tables, {"checks": []})
        finally:
            altered.close()

    def test_duplicate_keys_are_rejected(self):
        for table in database.TABLE_KEYS:
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(f"INSERT INTO {table} SELECT * FROM {table} LIMIT 1")

    def test_null_keys_are_rejected_without_generating_ids(self):
        for table in database.TABLE_KEYS:
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(f"UPDATE {table} SET customer_id = NULL WHERE customer_id = 1")

    def test_orphans_and_parent_deletion_are_rejected(self):
        absent_id = int(self.clean.customer_id.max()) + 1
        for table in ("monthly_repayments", "default_outcomes"):
            with self.subTest(table=table):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(f"UPDATE {table} SET customer_id = ? WHERE customer_id = 1", (absent_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("DELETE FROM customers WHERE customer_id = 1")

    def test_invalid_domains_and_fractional_amounts_are_rejected(self):
        cases = (
            ("monthly_repayments", "month", "2005-10"),
            ("monthly_repayments", "month", "2005-9"),
            ("monthly_repayments", "repayment_status", 10),
            ("monthly_repayments", "payment_amount_ntd", -1),
            ("monthly_repayments", "bill_amount_ntd", 1.5),
            ("default_outcomes", "default_next_month", 2),
            ("customers", "credit_limit_ntd", 0),
        )
        for table, column, value in cases:
            with self.subTest(table=table, column=column, value=value):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(f"UPDATE {table} SET {column} = ? WHERE customer_id = 1", (value,))

    def test_negative_bills_and_undocumented_codes_survive(self):
        monthly = self.tables["monthly_repayments"]
        negative_count = self.connection.execute(
            "SELECT COUNT(*) FROM monthly_repayments WHERE bill_amount_ntd < 0"
        ).fetchone()[0]
        self.assertGreater(negative_count, 0)
        self.assertEqual(negative_count, int(monthly.bill_amount_ntd.lt(0).sum()))
        for code in (-2, 0):
            with self.subTest(code=code):
                count = self.connection.execute(
                    "SELECT COUNT(*) FROM monthly_repayments WHERE repayment_status = ?", (code,)
                ).fetchone()[0]
                self.assertGreater(count, 0)
                self.assertEqual(count, int(monthly.repayment_status.eq(code).sum()))

    def test_offsetting_value_changes_are_detected_even_when_totals_match(self):
        # Swap two genuine values in the same month: aggregate checks alone miss this.
        for column in ("bill_amount_ntd", "repayment_status"):
            with self.subTest(column=column):
                self.connection.rollback()
                first_id, first_value = self.connection.execute(
                    f"SELECT customer_id, {column} FROM monthly_repayments WHERE month = '2005-09' ORDER BY customer_id LIMIT 1"
                ).fetchone()
                second_id, second_value = self.connection.execute(
                    f"SELECT customer_id, {column} FROM monthly_repayments WHERE month = '2005-09' AND {column} != ? ORDER BY customer_id LIMIT 1",
                    (first_value,),
                ).fetchone()
                total_before = self.connection.execute(f"SELECT SUM({column}) FROM monthly_repayments").fetchone()[0]
                self.connection.execute(
                    f"UPDATE monthly_repayments SET {column} = ? WHERE customer_id = ? AND month = '2005-09'",
                    (second_value, first_id),
                )
                self.connection.execute(
                    f"UPDATE monthly_repayments SET {column} = ? WHERE customer_id = ? AND month = '2005-09'",
                    (first_value, second_id),
                )
                self.assertEqual(total_before, self.connection.execute(f"SELECT SUM({column}) FROM monthly_repayments").fetchone()[0])
                with self.assertRaisesRegex(ValueError, "monthly_repayments: every value matches"):
                    database.validate_database(self.connection, self.tables, {"checks": []})

    def test_shifted_month_values_are_detected(self):
        april, september = self.connection.execute(
            "SELECT bill_amount_ntd FROM monthly_repayments WHERE customer_id = 1 AND month IN ('2005-04', '2005-09') ORDER BY month"
        ).fetchall()
        self.assertNotEqual(april[0], september[0])
        self.connection.execute(
            "UPDATE monthly_repayments SET bill_amount_ntd = CASE month WHEN '2005-04' THEN ? ELSE ? END "
            "WHERE customer_id = 1 AND month IN ('2005-04', '2005-09')", (september[0], april[0])
        )
        with self.assertRaisesRegex(ValueError, "monthly_repayments: every value matches"):
            database.validate_database(self.connection, self.tables, {"checks": []})

    def test_readonly_connection_does_not_create_missing_database(self):
        with tempfile.TemporaryDirectory(prefix="credit_risk_test_") as directory:
            temporary_root = Path(directory).resolve()
            self.assertEqual(temporary_root.parent, Path(tempfile.gettempdir()).resolve())
            missing = temporary_root / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                database.connect_database(missing, readonly=True)
            self.assertFalse(missing.exists())

    def test_failed_build_preserves_existing_database(self):
        # Redirect every build output into a verified temporary directory.
        # Check both a bad stage-2 checksum and a failure after candidate insertion.
        for failure in ("checksum", "candidate_validation"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(prefix="credit_risk_test_") as directory:
                root = Path(directory).resolve()
                self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
                published = root / "database" / "credit_risk.sqlite"
                published.parent.mkdir()
                copy = sqlite3.connect(published)
                try:
                    self.connection.backup(copy)
                finally:
                    copy.close()
                before = published.read_bytes()
                with ExitStack() as patches:
                    for name, value in (("PROJECT_ROOT", root), ("DATABASE_DIR", published.parent),
                                        ("DATABASE_PATH", published), ("REPORT_DIR", root / "reports")):
                        patches.enter_context(patch.object(database, name, value))
                    if failure == "checksum":
                        changed_csv = root / "changed.csv"
                        changed_csv.write_bytes(database.CLEAN_PATH.read_bytes() + b"\n")
                        original_loader = database.load_verified_clean
                        patches.enter_context(patch.object(
                            database, "load_verified_clean",
                            side_effect=lambda report: original_loader(report, clean_path=changed_csv),
                        ))
                        expected_message = "Clean CSV checksum matches"
                    else:
                        patches.enter_context(patch.object(database, "validate_database", side_effect=ValueError("Injected candidate failure")))
                        expected_message = "Injected candidate failure"
                    with self.assertRaisesRegex(ValueError, expected_message):
                        database.run()
                self.assertEqual(before, published.read_bytes())
                self.assertFalse(list(published.parent.glob("credit_risk_build_*")))
                report = json.loads((root / "reports" / "database_validation.json").read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "failed")


if __name__ == "__main__":
    unittest.main()
