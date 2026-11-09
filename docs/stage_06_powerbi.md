# Stage 6: Power BI exports and native report

Run `python -m src.export_powerbi` using the project's virtual-environment
interpreter. The export module verifies the source/database, builds four CSV
tables, checks keys and values, and reads each CSV back before publishing it.
The real export completed with **20 checks passed**.

```powershell
Set-Location 'C:\Users\Sachin\OneDrive\Documents\Desktop\DS_Project'
.\.venv\Scripts\python.exe -m src.export_powerbi
```

Outputs are `data/exports/customers.csv` (30,000 rows),
`monthly_repayments.csv` (180,000 rows), `default_outcomes.csv` (30,000 rows),
and `calendar_months.csv` (six rows). File hashes, row counts, provenance, and
filter-scenario reference numbers are recorded in
[`reports/powerbi_export_validation.json`](../reports/powerbi_export_validation.json).

Customers include fixed history features and sort-order fields. The future
target stays in the separate outcomes table. Monthly rows include the original
codes, amounts, an explicit status label, and a first-of-month grouping key.
This date is a reporting convention, not an invented transaction timestamp.

Generate the native report project after the exports pass:

```powershell
.\.venv\Scripts\python.exe -m src.build_powerbi_project
```

The generator creates
[`powerbi/Credit_Risk_Repayment_Analytics.pbip`](../powerbi/Credit_Risk_Repayment_Analytics.pbip)
and its sibling `.Report` and `.SemanticModel` folders. They contain four typed
Power Query imports, three single-direction relationships, 18 DAX measures,
and three report pages: portfolio, repayment history, and cohort investigation.
The DAX definitions come from [measures.dax](../powerbi/measures.dax), rather
than a second hand-maintained set of formulas.

Open the `.pbip` in Power BI Desktop and **Refresh**. If the workspace moves,
set the Power Query parameter `DataFolder` to the new absolute `data\exports`
directory through **Transform data > Manage Parameters**, then apply and
refresh. Complete the visual/filter checks in
[the dashboard guide](../powerbi/dashboard_guide.md), then use **Save As** to
save `powerbi/Credit_Risk_Repayment_Analytics.pbix`.

Close Desktop before rerunning the generator. It replaces its authored model
and visual definitions; preserve manual changes in a separate copy. The
Python pipeline does not refresh a saved PBIX or execute DAX automatically.

**Current state:** the native project and completed
[PBIX report](../powerbi/Credit_Risk_Repayment_Analytics.pbix) are saved.
The PBIX was reopened in Desktop, and all 90 numerical DAX checks passed
against its actual model (18 measures in five scenarios). See
`reports/powerbi_dax_validation.json` for the comparisons and
`reports/project_status.json` for report-file and runtime-verification flags.
The guide retains the from-scratch steps so you can explain and reproduce
the model yourself. The local Desktop report has not been published online.
All three pages rendered after reopening. The visual and filter observations,
saved-file integrity check, and file hashes are recorded in
[`powerbi_runtime_validation.json`](../reports/powerbi_runtime_validation.json).

Interview explanation: "I exported separate dimension and fact tables, chose
single-direction relationships, and wrote customer-level measures. For a
monthly-selected cohort I transferred distinct customer IDs to the outcome
table, rather than joining and summing a repeated default flag. I reconciled
the unfiltered and filtered counts against Python before building visuals."
