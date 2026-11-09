"""Stage 5: descriptive charts using verified UCI data at the correct grain."""

import json
import math
import os
from datetime import datetime, timezone

from .download_data import PROJECT_ROOT, sha256

# Configure a writable cache before importing plotting libraries.
CACHE_DIR = PROJECT_ROOT / ".cache" / "matplotlib"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(CACHE_DIR)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, StrMethodFormatter
import numpy as np
import pandas as pd
import seaborn as sns

from .analytics import CREDIT_BANDS, STATUS_GROUPS, load_analysis_data, status_group


REPORT_DIR = PROJECT_ROOT / "reports"
FIGURE_DIR = REPORT_DIR / "figures"
SOURCE_CAPTION = "Source: UCI 350, historical Taiwanese credit-card clients | History: April-September 2005."
BLUE = "#386B91"
ORANGE = "#C77B38"
GREY = "#A4ADB5"


def wilson_interval(defaults, customers, z=1.959963984540054):
    """95% Wilson binomial interval; descriptive uncertainty, not a causal test."""
    if customers <= 0 or defaults < 0 or defaults > customers:
        raise ValueError("Wilson interval needs 0 <= defaults <= customers and customers > 0.")
    rate = defaults / customers
    denominator = 1 + z * z / customers
    centre = (rate + z * z / (2 * customers)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / customers + z * z / (4 * customers**2)) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def summarize_rate(features, column, order):
    summary = features.groupby(column, observed=True).default_next_month.agg(customers="size", default_customers="sum")
    summary = summary.reindex([value for value in order if value in summary.index]).reset_index()
    if int(summary.customers.sum()) != len(features):
        raise ValueError(f"{column} groups do not cover all customers exactly once.")
    summary["default_rate"] = summary.default_customers / summary.customers
    intervals = [wilson_interval(int(row.default_customers), int(row.customers)) for row in summary.itertuples()]
    summary["ci_low"] = [value[0] for value in intervals]
    summary["ci_high"] = [value[1] for value in intervals]
    return summary


def summarize_monthly_mix(monthly):
    states = monthly.assign(
        paid_duly=monthly.repayment_status.eq(-1).astype(int),
        documented_delay=monthly.repayment_status.ge(1).astype(int),
        one_month_delay=monthly.repayment_status.eq(1).astype(int),
        undocumented=monthly.repayment_status.isin([-2, 0]).astype(int),
    )
    mix = states.groupby("month", as_index=False).agg(
        customers=("customer_id", "nunique"), records=("customer_id", "size"),
        paid_duly=("paid_duly", "sum"), documented_delay=("documented_delay", "sum"),
        one_month_delay=("one_month_delay", "sum"),
        undocumented=("undocumented", "sum"),
    )
    if not mix.customers.eq(mix.records).all():
        raise ValueError("A customer is counted more than once in a month.")
    if not mix[["paid_duly", "documented_delay", "undocumented"]].sum(axis=1).eq(mix.customers).all():
        raise ValueError("Monthly repayment categories are not an exhaustive partition.")
    for state in ("paid_duly", "documented_delay", "undocumented"):
        mix[f"{state}_share"] = mix[state] / mix.customers
    return mix.drop(columns="records")


def summarize_transitions(monthly):
    pair = monthly.loc[monthly.month.isin(["2005-08", "2005-09"])].pivot(
        index="customer_id", columns="month", values="repayment_status"
    )
    if pair.isna().any().any() or list(pair.columns) != ["2005-08", "2005-09"]:
        raise ValueError("Transitions require one August and one September record for every customer.")
    counts = pd.crosstab(pair["2005-08"].map(status_group), pair["2005-09"].map(status_group))
    counts = counts.reindex(index=STATUS_GROUPS, columns=STATUS_GROUPS, fill_value=0)
    denominators = counts.sum(axis=1)
    if denominators.eq(0).any():
        raise ValueError("A transition row has no observed customers; omit it before plotting.")
    shares = counts.div(denominators, axis=0)
    records = [
        {"august_status_group": august, "september_status_group": september,
         "customers": int(counts.loc[august, september]), "august_customers": int(denominators.loc[august]),
         "transition_share": float(shares.loc[august, september])}
        for august in STATUS_GROUPS for september in STATUS_GROUPS
    ]
    return counts, shares, records


def save_figure(figure, filename, subtitle):
    figure.text(0.02, 0.045, SOURCE_CAPTION, fontsize=8, color="#48525B")
    figure.text(0.02, 0.012, subtitle, fontsize=8, color="#48525B")
    figure.tight_layout(rect=(0, 0.105, 1, 1))
    path = FIGURE_DIR / filename
    figure.savefig(path, dpi=160, facecolor="white")
    plt.close(figure)
    return {"path": path.relative_to(PROJECT_ROOT).as_posix(), "sha256": sha256(path.read_bytes())}


def plot_rate(summary, group_column, title, group_axis_label, filename, footnote):
    figure, axis = plt.subplots(figsize=(10, 5.8))
    positions = np.arange(len(summary))
    rates = summary.default_rate.to_numpy() * 100
    errors = np.vstack([rates - summary.ci_low.to_numpy() * 100, summary.ci_high.to_numpy() * 100 - rates])
    axis.barh(positions, rates, color=BLUE, height=0.6)
    axis.errorbar(rates, positions, xerr=errors, fmt="none", color="#263743", capsize=3)
    axis.set_yticks(positions, summary[group_column].astype(str))
    axis.invert_yaxis()
    axis.set_xlim(0, 100)
    axis.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axis.set_xlabel("Next-month default rate (% of customers in segment)")
    axis.set_ylabel(group_axis_label)
    axis.set_title(title, loc="left", fontweight="bold", pad=15)
    axis.xaxis.grid(True, alpha=0.25)
    axis.yaxis.grid(False)
    for position, row in enumerate(summary.itertuples()):
        axis.text(row.ci_high * 100 + 1.2, position, f"{row.default_rate:.1%} | n={row.customers:,}", va="center", fontsize=9)
    return save_figure(figure, filename, "Error bars: 95% Wilson intervals. " + footnote)


def run():
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    report = {"stage": 5, "status": "failed", "run_at_utc": datetime.now(timezone.utc).isoformat(), "charts": []}
    try:
        data = load_analysis_data()
        features, monthly = data["customer_features"], data["monthly_repayments"]
        report["provenance"] = data["provenance"]
        report["customer_count"] = len(features)
        report["default_customers"] = int(features.default_next_month.sum())
        report["default_rate"] = float(features.default_next_month.mean())
        summaries = {
            "latest_status": summarize_rate(features, "latest_status_group", STATUS_GROUPS),
            "delayed_months": summarize_rate(features, "delayed_months", range(7)),
            "credit_limit_bands": summarize_rate(features, "credit_limit_band", CREDIT_BANDS),
            "zero_payment_months": summarize_rate(features, "zero_payment_months", range(7)),
        }
        mix = summarize_monthly_mix(monthly)
        counts, shares, transitions = summarize_transitions(monthly)
        if int(counts.to_numpy().sum()) != len(features):
            raise ValueError("Transition customer totals do not reconcile.")
        report["segments"] = {name: frame.to_dict(orient="records") for name, frame in summaries.items()}
        report["monthly_mix"] = mix.to_dict(orient="records")
        report["aug_sep_transitions"] = transitions
        sns.set_theme(style="whitegrid", context="notebook", font_scale=1.0)

        figure, axis = plt.subplots(figsize=(9, 5.6))
        outcome_counts = [int(features.default_next_month.eq(0).sum()), int(features.default_next_month.eq(1).sum())]
        bars = axis.bar(["No next-month default", "Next-month default"], outcome_counts, color=[BLUE, ORANGE], width=0.55)
        axis.bar_label(bars, labels=[f"{value:,} ({value / len(features):.2%})" for value in outcome_counts], padding=6)
        axis.set_ylim(0, max(outcome_counts) * 1.16)
        axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        axis.set_ylabel("Customers (count)")
        axis.set_xlabel("Observed next-month outcome")
        axis.set_title("Observed default outcomes: 30,000 customers", loc="left", fontweight="bold", pad=15)
        axis.xaxis.grid(False)
        report["charts"].append(save_figure(figure, "01_default_outcomes.png", "Each customer counted once. Sample default prevalence is not a Finnable portfolio estimate."))

        rate_specs = [
            ("latest_status", "latest_status_group", "Next-month default by September repayment status", "September 2005 status", "02_latest_status_default_rate.png", "Undocumented codes are shown separately; association does not imply causation."),
            ("delayed_months", "delayed_months", "Next-month default by frequency of documented delay", "Months with repayment code >= 1 (April-September)", "03_delayed_months_default_rate.png", "Zero documented-delay months can still include undocumented repayment codes."),
            ("credit_limit_bands", "credit_limit_band", "Next-month default by credit-limit band", "Credit-limit band (NTD)", "05_credit_limit_default_rate.png", "Fixed descriptive bands; this comparison is not adjusted for other customer differences."),
            ("zero_payment_months", "zero_payment_months", "Next-month default by zero-payment frequency", "Months with recorded payment = 0 (April-September)", "06_zero_payment_default_rate.png", "Zero recorded payment does not establish a missed contractual payment."),
        ]
        for key, column, title, ylabel, filename, note in rate_specs:
            report["charts"].append(plot_rate(summaries[key], column, title, ylabel, filename, note))

        figure, axis = plt.subplots(figsize=(10, 5.9))
        bottom = np.zeros(len(mix))
        for column, label, color in (("paid_duly_share", "Paid duly (-1)", BLUE),
                                     ("documented_delay_share", "Documented delay (1-9)", ORANGE),
                                     ("undocumented_share", "Undocumented (-2 / 0)", GREY)):
            height = mix[column].to_numpy() * 100
            axis.bar(mix.month, height, bottom=bottom, label=label, color=color, width=0.65)
            for position, (base, value) in enumerate(zip(bottom, height)):
                if value >= 8:
                    axis.text(position, base + value / 2, f"{value:.1f}%", ha="center", va="center", fontsize=9,
                              color="white" if color == BLUE else "#18232D")
            bottom += height
        axis.set_ylim(0, 100)
        axis.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        axis.set_xlabel("Repayment history month (2005)")
        axis.set_ylabel("Customers in each month (%)")
        axis.set_title("Monthly recorded repayment-status mix", loc="left", fontweight="bold", pad=40)
        axis.legend(loc="lower left", bbox_to_anchor=(0, 1.005), ncol=3, frameon=False, fontsize=9)
        axis.xaxis.grid(False)
        report["charts"].append(save_figure(figure, "04_monthly_status_mix.png", "n=30,000 per month. Code 1 frequency changes sharply; review coding before interpreting portfolio trends."))

        figure, axis = plt.subplots(figsize=(11, 7))
        annotation = np.array([[f"{shares.iloc[i, j]:.1%}\n{counts.iloc[i, j]:,} customers" for j in range(len(shares.columns))]
                               for i in range(len(shares.index))])
        sns.heatmap(shares * 100, annot=annotation, fmt="", cmap="Blues", vmin=0, vmax=100,
                    linewidths=0.6, linecolor="white", ax=axis, cbar_kws={"label": "Share of August segment (%)"}, annot_kws={"fontsize": 9})
        row_labels = [f"{group}\n(n={int(counts.loc[group].sum()):,})" for group in STATUS_GROUPS]
        axis.set_yticklabels(row_labels, rotation=0)
        axis.set_xticklabels(STATUS_GROUPS, rotation=20, ha="right")
        axis.set_xlabel("September 2005 repayment status")
        axis.set_ylabel("August 2005 repayment status (row denominator)")
        axis.set_title("August-to-September status transitions", loc="left", fontweight="bold", pad=15)
        report["charts"].append(save_figure(figure, "07_aug_sep_transitions.png", "Rows sum to 100%; every customer contributes one transition. Undocumented states are not cures or defaults."))

        report["charts"].sort(key=lambda item: item["path"])
        report["status"] = "passed"
        latest = summaries["latest_status"].set_index("latest_status_group")
        delayed = latest.loc["2+ months delay"]
        paid = latest.loc["Paid duly (-1)"]
        summary_text = f"""# Stage 5: exploratory analysis

Generated from validated UCI 350 data. Status: **passed**.
Run time (UTC): {report['run_at_utc']}.

- Customers: {len(features):,}; next-month defaults: {report['default_customers']:,} ({report['default_rate']:.2%}).
- September status of two or more months' documented delay: {int(delayed.default_customers):,} defaults among {int(delayed.customers):,} customers ({delayed.default_rate:.2%}).
- September paid-duly code -1: {int(paid.default_customers):,} defaults among {int(paid.customers):,} customers ({paid.default_rate:.2%}).
- One-month delay code 1 occurs for {int(mix.set_index('month').loc['2005-08', 'one_month_delay']):,} customers in August versus {int(mix.set_index('month').loc['2005-09', 'one_month_delay']):,} in September. Review timing and coding before interpreting the status-share change as deterioration.
- Seven PNG charts were generated in `reports/figures/`; their hashes and all plotted segment values are recorded in `reports/eda_summary.json`.

All customer-level rates count each customer once. Error bars use 95% Wilson
binomial intervals; they summarize sampling uncertainty under a binomial model,
not dataset representativeness, causal effects, or future portfolio performance.
Monthly status shares use 30,000 customers separately in each month. Transition
shares condition on the August category, with counts shown in every cell.

Undocumented codes remain separate. Zero documented-delay months do not imply
six on-time payments; zero recorded payments do not establish missed payments.
These are descriptive associations in historical Taiwanese credit-card data,
not Finnable customers. See `docs/stage_05_eda.md` for interpretation and commands.
"""
        (REPORT_DIR / "stage_05_summary.md").write_text(summary_text, encoding="utf-8")
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        (REPORT_DIR / "stage_05_summary.md").write_text(
            "# Stage 5: analysis failed\n\nSee reports/eda_summary.json. Existing figures may be from an earlier run.\n",
            encoding="utf-8",
        )
        raise
    finally:
        plt.close("all")
        (REPORT_DIR / "eda_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Stage 5 passed: {len(report['charts'])} charts; {report['customer_count']:,} customers; sample default rate {report['default_rate']:.2%}.")


if __name__ == "__main__":
    run()
