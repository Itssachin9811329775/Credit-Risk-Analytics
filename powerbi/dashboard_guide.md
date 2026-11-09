# Open, understand, and validate the Power BI report

This workspace includes the completed
[Power BI report](Credit_Risk_Repayment_Analytics.pbix), validated CSVs, and an
editable native project with three pages, 39 visuals, and 18 DAX measures.
The saved PBIX was reopened in Desktop; all 90 actual DAX checks passed against
independent Python calculations. Detailed numerical results are in
[`powerbi_dax_validation.json`](../reports/powerbi_dax_validation.json).
All three pages rendered after reopening. Visual/filter checks and hashes of
the saved report and inputs are recorded in
[`powerbi_runtime_validation.json`](../reports/powerbi_runtime_validation.json).

Use Power BI Desktop on Windows. This report concerns historical Taiwanese
credit-card customers from UCI, not Finnable customers. Amounts are NTD, not INR.
Each page includes its source, period, currency, and interpretation limits.

## Open the completed report

Open [Credit_Risk_Repayment_Analytics.pbix](Credit_Risk_Repayment_Analytics.pbix)
in Power BI Desktop. The imported data is included, so you can explore all
three pages without refreshing. Refresh requires access to the exported CSVs;
if you move the workspace, update `DataFolder` as explained below. The report
is saved locally and has not been published to the Power BI service.

## Reproduce from the editable native project

1. Open [Credit_Risk_Repayment_Analytics.pbip](Credit_Risk_Repayment_Analytics.pbip)
   in Power BI Desktop. Keep its sibling `.Report` and `.SemanticModel` folders
   beside it. The `.pbip` is a project entry point, not a self-contained report.
2. Choose **Refresh** (or **Refresh now** on the incomplete-data banner) to
   import the four CSVs. If Desktop shows pending query changes, apply them.
3. If the workspace moved, choose **Transform data > Manage Parameters** and
   set `DataFolder` to the full path of its `data\exports` folder, without a
   trailing slash. Choose **Close & Apply**, then refresh.
4. Explore **01 Portfolio**, **02 Repayment history**, and
   **03 Cohort investigation**. The native project already contains the
   relationships, types, sort columns, measures, and visuals described below.
5. Reconcile the scenarios in section 6. For exact unrounded model outputs,
   run [validation_queries.dax](validation_queries.dax) in **DAX query view**.
   This file is one runnable query; `measures.dax` contains separate measure
   definitions instead.
6. Use **File > Save As**, select **Power BI report (*.pbix)**, and save as
   `powerbi\Credit_Risk_Repayment_Analytics.pbix`. Verify that the saved file
   reopens with its data and all three pages. A saved PBIX contains imported
   data for viewing; refreshing still requires the CSV paths to resolve.

To regenerate the project from code, close it in Desktop and run:

```powershell
.\.venv\Scripts\python.exe -m src.export_powerbi
.\.venv\Scripts\python.exe -m src.build_powerbi_project
```

The generator replaces its authored model and visual definitions. Preserve a
separate copy before making manual changes that you want to retain. Refresh
the reopened report after changing exports. No sign-in or publishing is needed
for the local report workflow.
If Desktop converted the semantic model to TMDL, the generator first moves
that definition into `.cache/powerbi_backups` before writing model.bim. This
prevents conflicting model formats and preserves a recoverable copy.

The following sections explain the same model from scratch for interview
preparation. When using the generated project, inspect the existing setup
instead of adding duplicate queries, relationships, or measures.

## 1. Generate the inputs

From Windows PowerShell in the project root:

```powershell
.\.venv\Scripts\python.exe -m src.export_powerbi
```

Confirm `reports/powerbi_export_validation.json` says `"status": "passed"`.
The four files under `data/exports/` are:

- `customers.csv`: 30,000 customer rows, enriched with fixed history features.
- `monthly_repayments.csv`: 180,000 customer-month rows.
- `default_outcomes.csv`: 30,000 future outcome rows, one per customer.
- `calendar_months.csv`: six month keys, April through September 2005.

The next-month outcome is deliberately absent from customers and monthly rows.
`month_start` is a first-of-month grouping key, not an observed transaction date.

## 2. Import and set types when building from scratch

1. In a blank Power BI Desktop report, choose **Get data > Text/CSV**. Select
   `data/exports/customers.csv`, then **Transform Data**. Repeat for the other
   three CSVs. Keep query names exactly `customers`, `monthly_repayments`,
   `default_outcomes`, and `calendar_months`.
2. Confirm UTF-8 encoding and comma separation. The first row supplies headers.
   Inspect the automatically added Changed Type step and correct it explicitly.
3. Use **Whole number** for IDs, raw codes, age, amounts ending `_ntd`, history
   counts, flag columns, and columns ending `_order`. Set
   `customers[latest_bill_to_limit]` to **Decimal number**. Keep labels, `month`,
   and status-group columns as **Text**.
4. Set both `monthly_repayments[month_start]` and
   `calendar_months[month_start]` to **Date**, using the ISO YYYY-MM-DD input.
   Do not create dates for the default outcome.
5. Choose **Close & Apply**. If files move, update each query's Source path in
   Power Query and refresh. The CSVs are reproducible inputs, not live database
   connections.
6. Disable automatic date/time tables for this file if enabled. The six-row
   calendar is a month dimension, not a contiguous daily date table: do not
   mark it as a Date table or add daily time-intelligence measures.

## 3. Create exactly three relationships

In **Model view > Manage relationships**, remove conflicting auto-detected
relationships and create these active relationships:

- `customers[customer_id]` **1 -> many**, Single direction, to
  `monthly_repayments[customer_id]`.
- `customers[customer_id]` **1 -> many**, Single direction, to
  `default_outcomes[customer_id]`. Outcome IDs happen to be unique, but choose
  one-to-many explicitly so filters flow only from customers to outcomes.
- `calendar_months[month_start]` **1 -> many**, Single direction, to
  `monthly_repayments[month_start]`.

Do not connect calendar to outcomes or monthly directly to outcomes. Keep
bidirectional filtering off. Customer filters then reach both fact tables;
history filters reach the monthly fact only. Microsoft explains filter paths
and relationship cardinality in its
[relationship documentation](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-relationships-understand).
Relationships do not substitute for the Python key and coverage validation.

In the model, set category codes and IDs to **Don't summarize**. Hide technical
keys and ordering columns from report authors where practical. Use
**Sort by column** to sort `customers[credit_limit_band]`, `[age_band]`, and
`[latest_status_group]` by the matching `_order` column. Sort
`calendar_months[month_label]` by `[month_order]`.

## 4. Add and format the measures when building from scratch

Open [measures.dax](measures.dax). Select a table and use **Modeling > New measure**
for each definition separately, in the listed order. The file is a reference
of individual measures, not a script to paste as one giant expression.

- Format `Default Rate`, `Documented Delay Share`, `Undocumented Status Share`,
  and `Selected History Cohort Default Rate` as Percentage with two decimals.
- Format count measures as whole numbers with thousands separators.
- Format NTD measures as whole numbers with separators and NTD in the visual
  title. Do not apply an Indian currency symbol.

`CALCULATE` changes filter context; `KEEPFILTERS` intersects a measure's condition
with an existing selection. See
[CALCULATE](https://learn.microsoft.com/en-us/dax/calculate-function-dax).
The cohort measures pass distinct IDs from the filtered monthly table to the
outcome/customer table using
[TREATAS](https://learn.microsoft.com/en-us/dax/treatas-function-dax).
They transfer a selection, not 180,000 repeated rows.

`Single Month Bill NTD` returns blank unless exactly one calendar month is in
context. This uses
[HASONEVALUE](https://learn.microsoft.com/en-us/dax/hasonevalue-function-dax)
to avoid presenting the sum of six bill snapshots as outstanding debt.
An unfiltered monthly chart still has one month per data point, so the measure
can display each point while leaving a multi-month total card blank.

## 5. Understand or rebuild the three report pages

### Page 1: portfolio overview

1. Add cards for `Customer Count`, `Defaulting Customers`, `Default Rate`, and
   `Credit Limit NTD`. Title the last card **Sum of credit limits (NTD)**.
2. Add a bar chart with `customers[latest_status_group]` as the category and
   `Default Rate` as the value. Use `Customer Count` in the tooltip to expose
   the denominator. Title it **Default rate by September repayment status**.
   The rate is a fraction formatted as a percentage.
3. Add a column chart for `customers[delayed_months]` and `Default Rate`, with
   customer count as a tooltip. Title it **Next-month default by number
   of months with documented delay**. Zero delayed months does not establish
   on-time repayment because undocumented codes remain present.
4. Add customer slicers for `credit_limit_band` and `age_band`. These are
   descriptive segments, not validated lending-decision rules.
5. Add a note: **Customer features summarize Apr-Sep or September specifically;
   they do not change when a history-month slicer changes. Associations are not
   evidence of causal effects.**

### Page 2: recorded repayment history

1. Add a 100% stacked column chart: axis `calendar_months[month_label]`, legend
   `monthly_repayments[repayment_status_group]`, value `Monthly Rows`.
   Keep undocumented -2 and 0 visible, with distinct neutral colours.
2. Add a line chart of `Documented Delay Share` by calendar month. Add
   `Monthly Rows` to the tooltip and label it **Share of rows with documented
   delay (codes 1+)**.
3. Add cards for `Monthly Rows`, `Monthly Customers`,
   `Undocumented Status Share`, and `Recorded Payments NTD`. Recorded payments
   are not recoveries attributable to collections intervention.
4. Add a calendar month slicer that permits several months, plus a
   `Single Month Bill NTD` card. The card intentionally stays blank until
   exactly one month is selected. Multi-month selection lets you compare the
   history charts while retaining the guard against summing bill snapshots.
   Negative bill values remain included; no refund/credit explanation is assumed.
5. Add a prominent comparability note: **Code 1 occurs 28 times in August and
   3,688 times in September. Recorded delay share moves from 14.79% to 22.73%,
   but this cannot establish worsening repayment behaviour without confirming
   recording conventions and measurement timing.**

### Page 3: cohort investigation for collections discussion

1. Add slicers for calendar month, `monthly_repayments[repayment_status_group]`,
   and `customers[credit_limit_band]`.
2. Add cards for `Selected History Customers`,
   `Defaults in Selected History Cohort`, `Selected History Cohort Default Rate`,
   and `Credit Limit in Selected History Cohort NTD`.
3. Add a table grouped by `customers[credit_limit_band]`, with
   `Selected History Customers`, `Defaults in Selected History Cohort`, and
   `Selected History Cohort Default Rate`. This presents segment denominators
   without turning the report into an individual contact list.
4. Add a note: **This is an exploratory historical cohort, not a deployment-ready
   collections queue. The file does not contain contact attempts, amounts due,
   intervention costs, or causal recovery outcomes.**

The page also includes `Default Rate`, labelled **Base customer-segment rate**.
It intentionally does not respond to month or
monthly-status selections. The explicit cohort rate does. With several months
selected, the cohort is the union of customers meeting the history selection,
counted once. It is not a set of distinct monthly default outcomes.

## 6. Reconcile before saving

These are independently derived Python/SQL expected values. Desktop validation
is recorded separately; use `reports/powerbi_export_validation.json` for exact
unrounded reference values and `validation_queries.dax` to query the actual
model. Set count-card display units to **None** when checking exact counts.

- **Clear all filters:** 30,000 customers, 6,636 defaults, 22.12% default rate,
  credit limits 5,024,529,680 NTD, 180,000 monthly rows, 30,000 monthly customers.
  The single-month bill card must be blank.
- **September only:** 30,000 monthly rows; 6,818 recorded-delay rows;
  17,496 undocumented-status rows; 5,686 paid-duly rows; bill sum
  1,536,699,927 NTD. Base default rate remains 22.12%.
- **September and 2+ months delay:** 3,130 distinct cohort customers,
  2,177 defaulting cohort customers, cohort default rate **69.55%**.
  The base customer count/rate still show 30,000 / 22.12%.
- **Also choose Below 50k:** the base segment has 4,311 customers, 1,555 defaults,
  a 36.07% base rate; the selected history cohort has 853 customers and
  597 defaults, or **69.99%**. This checks the intersection of customer and
  history filters.
- **Select two months:** the bill total card returns blank; cohort customers
  are distinct across the two months and never counted twice.

If a number disagrees, first inspect types, active relationship directions,
visual filters/interactions, and whether the intended base or cohort measure
is being used. Do not change the source to match an incorrect visual.

## 7. Finish the artifact in Power BI

Use clear titles, consistent colours, percentage formatting, count tooltips,
and a source/limitations note on each page. Save the finished report
as `powerbi/Credit_Risk_Repayment_Analytics.pbix` after all checks pass. The repo
ignores `.pbix` binaries by default; decide deliberately how to share that file.
No publishing, service upload, or external sharing is performed by these scripts.

For an interview: **I used a customer dimension to filter repayment and outcome
facts separately. I kept monthly observations and customer outcomes at their
own grains, and transferred distinct customer IDs only when a cohort measure
needed a monthly selection. That avoids multiplying default counts by six.**
