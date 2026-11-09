"""Exercise validation with in-memory changes to the authentic cached UCI data.

These tests never download data or change raw/processed project files. Mutated
copies are deliberately invalid test inputs, not portfolio observations.
"""

import unittest

import pandas as pd

from src.download_data import MANIFEST_PATH, WORKBOOK_PATH, verify_cached_download
from src.prepare_data import (
    BILL_COLUMNS,
    STATUS_COLUMNS,
    TARGET,
    clean_data,
    column_mapping,
    validate_raw,
)


class DataPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WORKBOOK_PATH.is_file() or not MANIFEST_PATH.is_file():
            raise unittest.SkipTest(
                "Verified UCI workbook is absent; run stage 2 before these offline tests."
            )
        verify_cached_download()
        cls.original = pd.read_excel(WORKBOOK_PATH, sheet_name="Data", header=1, engine="xlrd")

    def assert_rejected(self, changed, expected_check):
        report = {"checks": []}
        with self.assertRaisesRegex(ValueError, expected_check):
            validate_raw(changed, report)
        self.assertEqual(report["checks"][-1]["name"], expected_check)
        self.assertFalse(report["checks"][-1]["passed"])

    def test_authentic_workbook_passes(self):
        report = {"checks": []}
        validate_raw(self.original, report)
        self.assertTrue(report["checks"])
        self.assertTrue(all(check["passed"] for check in report["checks"]))

    def test_duplicate_customer_id_is_rejected(self):
        changed = self.original.copy()
        changed.loc[0, "ID"] = changed.loc[1, "ID"]
        self.assert_rejected(changed, "Unique positive customer IDs")

    def test_missing_value_is_rejected(self):
        changed = self.original.copy()
        changed["AGE"] = changed["AGE"].astype("float64")
        changed.loc[0, "AGE"] = float("nan")
        self.assert_rejected(changed, "No missing values")

    def test_invalid_target_is_rejected(self):
        changed = self.original.copy()
        changed.loc[0, TARGET] = 2
        self.assert_rejected(changed, "Binary target")

    def test_fractional_numeric_value_is_rejected(self):
        changed = self.original.copy()
        changed["LIMIT_BAL"] = changed["LIMIT_BAL"].astype("float64")
        changed.loc[0, "LIMIT_BAL"] += 0.5
        self.assert_rejected(changed, "Finite integer values")

    def test_infinite_numeric_value_is_rejected(self):
        changed = self.original.copy()
        changed["LIMIT_BAL"] = changed["LIMIT_BAL"].astype("float64")
        changed.loc[0, "LIMIT_BAL"] = float("inf")
        self.assert_rejected(changed, "Finite integer values")

    def test_negative_payment_is_rejected(self):
        changed = self.original.copy()
        changed.loc[0, "PAY_AMT1"] = -1
        self.assert_rejected(changed, "Nonnegative payment amounts")

    def test_integer_overflow_is_rejected_before_casting(self):
        changed = self.original.copy()
        changed["BILL_AMT1"] = changed["BILL_AMT1"].astype("float64")
        changed.loc[0, "BILL_AMT1"] = float(2**63)
        self.assert_rejected(changed, "Finite integer values")

    def test_unexpected_category_codes_are_rejected(self):
        cases = (
            ("SEX", 3, "Recognised sex codes"),
            ("EDUCATION", 7, "Education codes inspected"),
            ("MARRIAGE", 4, "Marriage codes inspected"),
            ("PAY_0", 10, "Repayment codes inspected"),
        )
        for column, invalid_code, expected_check in cases:
            with self.subTest(column=column):
                changed = self.original.copy()
                changed.loc[0, column] = invalid_code
                self.assert_rejected(changed, expected_check)

    def test_known_undocumented_codes_are_preserved_and_labelled(self):
        clean = clean_data(self.original).set_index("customer_id")
        cases = (
            ("EDUCATION", "education", (0, 5, 6)),
            ("MARRIAGE", "marriage", (0,)),
        )
        for source, prefix, codes in cases:
            for code in codes:
                with self.subTest(source=source, code=code):
                    ids = self.original.loc[self.original[source].eq(code), "ID"]
                    self.assertGreater(len(ids), 0, "This check must exercise observed UCI records.")
                    self.assertTrue(clean.loc[ids, f"{prefix}_code"].eq(code).all())
                    self.assertTrue(
                        clean.loc[ids, f"{prefix}_label"].eq(f"Undocumented (code {code})").all()
                    )

        mapping = column_mapping()
        for column in STATUS_COLUMNS:
            for code in (-2, 0):
                with self.subTest(source=column, code=code):
                    ids = self.original.loc[self.original[column].eq(code), "ID"]
                    self.assertGreater(len(ids), 0)
                    self.assertTrue(clean.loc[ids, mapping[column]].eq(code).all())
                    self.assertTrue(clean.loc[ids, "has_undocumented_repayment_code"].all())

    def test_negative_bills_are_retained_and_flagged(self):
        clean = clean_data(self.original).set_index("customer_id")
        original = self.original.set_index("ID")
        mapping = column_mapping()
        for column in BILL_COLUMNS:
            with self.subTest(source=column):
                negative = original.loc[original[column].lt(0), column]
                self.assertGreater(len(negative), 0)
                self.assertEqual(clean.loc[negative.index, mapping[column]].tolist(), negative.tolist())
                self.assertTrue(clean.loc[negative.index, "has_negative_bill"].all())

    def test_distinct_ids_with_identical_predictors_are_not_dropped(self):
        repeated = self.original.drop(columns=["ID", TARGET]).duplicated(keep=False)
        ids = self.original.loc[repeated, "ID"]
        self.assertGreater(len(ids), 1, "This check must exercise real matching profiles.")
        self.assertTrue(ids.is_unique)
        clean = clean_data(self.original)
        self.assertEqual(len(clean), len(self.original))
        self.assertTrue(clean["customer_id"].is_unique)
        self.assertEqual(set(clean.loc[clean["customer_id"].isin(ids), "customer_id"]), set(ids))


if __name__ == "__main__":
    unittest.main()
