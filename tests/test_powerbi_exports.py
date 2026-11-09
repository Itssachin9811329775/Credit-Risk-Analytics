"""Test export integrity and reference filter semantics without a DAX runtime."""

import unittest

import pandas as pd

from src.analytics import load_analysis_data
from src.export_powerbi import make_exports, reference_metrics, validate_exports


class PowerBIExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.data = load_analysis_data()
        except FileNotFoundError as exc:
            raise unittest.SkipTest("Run stages 2 and 3 before export tests.") from exc
        cls.tables = make_exports(cls.data)

    def test_exported_grains_and_target_separation(self):
        report = {"checks": []}
        validate_exports(self.tables, self.data, report)
        self.assertTrue(all(row["passed"] for row in report["checks"]))
        self.assertNotIn("default_next_month", self.tables["customers"])
        self.assertNotIn("default_next_month", self.tables["monthly_repayments"])

    def test_multiple_months_do_not_duplicate_cohort_customers(self):
        result = reference_metrics(self.tables, months=["2005-08", "2005-09"])
        self.assertEqual(result["monthly_rows"], 60_000)
        self.assertEqual(result["cohort_customers"], 30_000)
        self.assertEqual(result["cohort_defaulting_customers"], 6_636)
        self.assertIsNone(result["single_month_bill_ntd"])

    def test_september_cohort_matches_direct_clean_feature_filter(self):
        result = reference_metrics(self.tables, months=["2005-09"], status_groups=["2+ months delay"])
        features = self.data["customer_features"]
        expected = features.loc[features.latest_repayment_status.ge(2)]
        self.assertEqual(result["cohort_customers"], len(expected))
        self.assertEqual(result["cohort_defaulting_customers"], int(expected.default_next_month.sum()))
        self.assertEqual(result["customer_count"], len(features))
        self.assertEqual(result["defaulting_customers"], int(features.default_next_month.sum()))

    def test_customer_and_history_filters_intersect(self):
        features = self.data["customer_features"]
        below_50k = features.loc[features.credit_limit_ntd.lt(50_000)]
        result = reference_metrics(self.tables, customer_ids=below_50k.customer_id,
                                   months=["2005-09"], status_groups=["2+ months delay"])
        expected = below_50k.loc[below_50k.latest_repayment_status.ge(2)]
        self.assertEqual(result["customer_count"], len(below_50k))
        self.assertEqual(result["cohort_customers"], len(expected))
        self.assertEqual(result["cohort_defaulting_customers"], int(expected.default_next_month.sum()))

    def test_duplicate_monthly_key_is_rejected(self):
        changed = self.tables.copy()
        changed["monthly_repayments"] = pd.concat([changed["monthly_repayments"], changed["monthly_repayments"].iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Customer-month key"):
            validate_exports(changed, self.data, {"checks": []})

    def test_altered_value_is_rejected(self):
        changed = self.tables.copy()
        changed["monthly_repayments"] = changed["monthly_repayments"].copy()
        changed["monthly_repayments"].loc[0, "bill_amount_ntd"] += 1
        with self.assertRaisesRegex(ValueError, "Original monthly values preserved"):
            validate_exports(changed, self.data, {"checks": []})

    def test_empty_history_cohort_does_not_change_base_outcome(self):
        result = reference_metrics(self.tables, months=["2005-09"], status_groups=["nonexistent"])
        self.assertEqual(result["cohort_customers"], 0)
        self.assertIsNone(result["cohort_default_rate"])
        self.assertEqual(result["defaulting_customers"], 6_636)


if __name__ == "__main__":
    unittest.main()
