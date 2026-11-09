"""Check business-query denominators and reject corrupted aggregate results."""

import unittest

import pandas as pd

from src.analytics import load_analysis_data
from src.build_database import DATABASE_PATH, connect_database
from src.run_sql_analysis import execute_queries, validate_results


class SqlAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DATABASE_PATH.exists():
            raise unittest.SkipTest("Run stages 2 and 3 before these offline SQL tests.")
        cls.data = load_analysis_data()
        connection = connect_database(DATABASE_PATH, readonly=True)
        try:
            cls.results = execute_queries(connection)
        finally:
            connection.close()

    def test_all_queries_match_independent_dataframe_calculations(self):
        checks = validate_results(self.results, self.data)
        self.assertEqual(len(checks), 10)
        self.assertTrue(all(item["passed"] for item in checks))

    def test_customer_segments_partition_customers_and_outcomes(self):
        for name, frame in self.results.items():
            if name == "05_monthly_status_mix":
                continue
            with self.subTest(query=name):
                self.assertEqual(int(frame.customers.sum()), len(self.data["customers"]))
                self.assertEqual(int(frame.default_customers.sum()), int(self.data["default_outcomes"].default_next_month.sum()))
                weighted_rate = (frame.default_rate * frame.customers).sum() / frame.customers.sum()
                self.assertAlmostEqual(weighted_rate, self.data["default_outcomes"].default_next_month.mean(), places=12)

    def test_monthly_status_categories_are_disjoint_and_complete(self):
        frame = self.results["05_monthly_status_mix"]
        self.assertEqual(list(frame.month), ["2005-04", "2005-05", "2005-06", "2005-07", "2005-08", "2005-09"])
        self.assertTrue(frame.customers.eq(len(self.data["customers"])).all())
        partition = frame.paid_duly_customers + frame.documented_delay_customers + frame.undocumented_customers
        self.assertTrue(partition.equals(frame.customers))
        self.assertTrue(frame.two_plus_delay_customers.le(frame.documented_delay_customers).all())

    def test_fixed_month_transitions_have_one_pair_per_customer(self):
        transitions = self.results["06_aug_sep_transitions"]
        by_september = transitions.groupby("september_status_group")[["customers", "default_customers"]].sum().sort_index()
        september = self.results["02_latest_repayment_status"].set_index("status_group")[["customers", "default_customers"]].sort_index()
        by_september.index.name = september.index.name
        pd.testing.assert_frame_equal(by_september, september)

    def test_decile_capture_is_a_partition_not_repeated_outcomes(self):
        frame = self.results["09_history_priority_deciles"]
        self.assertEqual(list(frame.priority_decile), list(range(1, 11)))
        self.assertTrue(frame.customers.eq(len(self.data["customers"]) // 10).all())
        self.assertAlmostEqual(frame.default_capture_share.sum(), 1.0, places=12)
        self.assertAlmostEqual(frame.cumulative_default_capture_share.iloc[-1], 1.0, places=12)
        self.assertTrue(frame.cumulative_default_capture_share.is_monotonic_increasing)

    def test_negative_bill_customers_remain_a_separate_segment(self):
        features = self.data["customer_features"]
        negative = features.loc[features.latest_bill_amount_ntd.lt(0)]
        result = self.results["07_september_bill_to_limit"].set_index("bill_to_limit_band").loc["Negative bill"]
        self.assertGreater(len(negative), 0)
        self.assertEqual(int(result.customers), len(negative))
        self.assertEqual(int(result.default_customers), int(negative.default_next_month.sum()))

    def test_plausible_but_wrong_default_count_is_rejected(self):
        altered = {name: frame.copy() for name, frame in self.results.items()}
        altered["02_latest_repayment_status"].loc[0, "default_customers"] += 1
        # Keep the modified rate internally consistent; independent source reconciliation must still reject it.
        frame = altered["02_latest_repayment_status"]
        frame.loc[0, "default_rate"] = frame.loc[0, "default_customers"] / frame.loc[0, "customers"]
        with self.assertRaises(AssertionError):
            validate_results(altered, self.data)

    def test_duplicate_segment_key_is_rejected(self):
        altered = {name: frame.copy() for name, frame in self.results.items()}
        altered["03_credit_limit_bands"] = pd.concat(
            [altered["03_credit_limit_bands"], altered["03_credit_limit_bands"].iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplicate segment keys"):
            validate_results(altered, self.data)


if __name__ == "__main__":
    unittest.main()
