"""Check EDA denominators and intervals without exporting charts or fake records."""

import unittest

from src.analytics import STATUS_GROUPS, load_analysis_data
from src.build_database import DATABASE_PATH
from src.explore_data import summarize_monthly_mix, summarize_rate, summarize_transitions, wilson_interval


class WilsonIntervalTests(unittest.TestCase):
    def test_boundary_counts_have_non_degenerate_intervals(self):
        low, high = wilson_interval(0, 100)
        self.assertAlmostEqual(low, 0)
        self.assertAlmostEqual(high, 0.0369935, places=6)
        low, high = wilson_interval(100, 100)
        self.assertAlmostEqual(low, 0.9630065, places=6)
        self.assertAlmostEqual(high, 1)

    def test_invalid_denominators_are_rejected(self):
        for successes, total in ((0, 0), (-1, 10), (11, 10)):
            with self.subTest(successes=successes, total=total), self.assertRaises(ValueError):
                wilson_interval(successes, total)


class ExplorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DATABASE_PATH.exists():
            raise unittest.SkipTest("Build the real UCI database before running EDA checks.")
        cls.data = load_analysis_data()

    def test_segment_counts_and_outcomes_reconcile(self):
        features = self.data["customer_features"]
        summary = summarize_rate(features, "latest_status_group", STATUS_GROUPS)
        self.assertEqual(int(summary.customers.sum()), len(features))
        self.assertEqual(int(summary.default_customers.sum()), int(features.default_next_month.sum()))
        self.assertTrue(summary.ci_low.le(summary.default_rate).all())
        self.assertTrue(summary.ci_high.ge(summary.default_rate).all())
        # Independent filter against raw monthly September codes.
        ids = self.data["monthly_repayments"].query("month == '2005-09' and repayment_status >= 2").customer_id
        expected = self.data["default_outcomes"].set_index("customer_id").loc[ids].default_next_month
        observed = summary.set_index("latest_status_group").loc["2+ months delay"]
        self.assertEqual(observed.customers, len(ids))
        self.assertEqual(observed.default_customers, int(expected.sum()))

    def test_monthly_states_partition_each_month(self):
        mix = summarize_monthly_mix(self.data["monthly_repayments"])
        self.assertEqual(len(mix), 6)
        self.assertTrue(mix.customers.eq(len(self.data["customers"])).all())
        self.assertTrue(mix[["paid_duly", "documented_delay", "undocumented"]].sum(axis=1).eq(mix.customers).all())
        self.assertGreater(int(mix.undocumented.sum()), 0)

    def test_transition_denominators_are_august_cohorts(self):
        counts, shares, records = summarize_transitions(self.data["monthly_repayments"])
        self.assertEqual(int(counts.to_numpy().sum()), len(self.data["customers"]))
        self.assertTrue(shares.sum(axis=1).sub(1).abs().lt(1e-12).all())
        self.assertEqual(len(records), 25)
        for row in records:
            self.assertAlmostEqual(row["transition_share"], row["customers"] / row["august_customers"])


if __name__ == "__main__":
    unittest.main()
