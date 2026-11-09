# Stage 2: download, inspect, clean, and validate

Stage 2 is complete. The pipeline has run on the actual downloaded UCI file and
passed 20 structural, numeric, preservation, and export checks. The purpose is
to make the data trustworthy before building SQLite tables or analysing risk.

## Run it in Windows PowerShell

```powershell
Set-Location 'C:\Users\Sachin\OneDrive\Documents\Desktop\DS_Project'
.\.venv\Scripts\python.exe -m src.prepare_data
```

The first run needs internet access. Later runs reuse the raw download after
checking both SHA-256 hashes. This project already has the real source files;
you can run entirely offline:

```powershell
.\.venv\Scripts\python.exe -m src.prepare_data --offline
```

Success ends with `Stage 2 passed: 20 checks; 30,000 customers; 30 clean columns.`
It also prints the sample default rate and paths to the CSV and quality summary.
No new dependency is required. The first download in this session required
network approval because the execution sandbox blocked outbound access.

## What the code does

1. `src/download_data.py` downloads the official ZIP, reads only the expected XLS
   member, and preserves both byte-for-byte. It records retrieval metadata and
   SHA-256 hashes. Existing raw files are never silently replaced. A changed
   checksum, incomplete download, or missing provenance stops the pipeline.
2. `src/prepare_data.py` reads sheet `Data` with `header=1`, because the real
   headers are on the second Excel row. It requires the inspected 25-column
   schema and 30,000 rows. It checks missingness, data types, unique IDs, target
   codes, and numeric ranges before transforming anything.
3. It keeps all original numeric values, gives columns clearer names, adds three
   category labels and two quality flags, and sorts the output by customer ID.
4. It checks every source numeric value against the corresponding cleaned value.
   It writes a temporary CSV, reads it back, and checks equality before replacing
   the clean output. The resulting file contains exactly one row per customer.
5. It writes inspection reports, a dictionary, and explicit month mappings.
   Each run updates `reports/data_quality.json` with a passed or failed status.

These checks establish the local file's integrity and consistency. They cannot
prove that the original data collection was error-free or representative.

## Files to inspect

- `data/raw/uci_350_original.zip`: unchanged downloaded archive.
- `data/raw/default of credit card clients.xls`: unchanged workbook from it.
- `data/raw/source_manifest.json`: source, retrieval time, sizes, and hashes.
- `data/processed/credit_clients_clean.csv`: 30,000 customers, 30 columns.
- `data/processed/data_dictionary.csv`: every output column, source, type, unit,
  and meaning.
- `data/processed/month_mapping.csv`: six explicit monthly mappings, ordered
  April through September; it contains metadata, not customer repayment rows.
- `reports/column_profile.csv`: observed types, distinct counts, missing values,
  ranges, zero counts, and negative counts for each source column.
- `reports/category_counts.csv`: counts of each code in each categorical source
  field, including whether the UCI description defines that code.
- `reports/data_quality.json`: machine-readable source metadata, checks, observed
  counts, and the clean file's SHA-256.
- `reports/stage_02_summary.md`: readable observations generated from the data.

The raw and processed data folders are ignored by Git. The reports include the
source provenance so the project remains reviewable, and the commands regenerate
the local data files from the official source.

## Cleaning decisions you should be able to defend

**No imputation:** the parsed source has zero missing cells. Inventing replacement
values would add no value. Undocumented codes are a semantic-quality problem,
even though they are not blank cells.

**No rows removed:** the IDs are unique. There are 35 repeated profiles after
excluding ID, and 56 after also excluding the target; these count occurrences
after the first in each matching group. Matching attributes do not establish
that different IDs are duplicate customers. All 30,000 IDs remain in the output.

**Preserve category codes:** education codes 0, 5, and 6 occur 14, 280, and 51
times. Marriage code 0 occurs 54 times. The original numeric values are retained;
the added labels explicitly say `Undocumented (code ...)`. Documented `Other`
categories remain distinct from undocumented categories.

**Preserve negative bills:** 3,932 monthly bill entries are negative, affecting
1,930 customers. This alone does not prove an error. Their exact meaning cannot
be established from the dataset, so the values are kept and `has_negative_bill`
flags the affected customers. No negative payment amounts were observed.

**Preserve repayment semantics:** codes -2 and 0 lack definitions in the official
variable description. The pipeline does not assume they mean on-time, revolving
credit, or no consumption. `has_undocumented_repayment_code` identifies customers
with at least one such code. Future analyses must distinguish documented delays,
documented paid-duly status, and undocumented states. See the
[official variable descriptions](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients).

**Map time explicitly:** the source uses `PAY_0` for the latest month, while its
bill and payment fields use suffix 1. The mapping CSV prevents accidentally
shifting payment status by one month. There is no `PAY_1` column. No new outcome
date is invented; `default_next_month` remains the source's one future target.

**Do not fit anything:** this stage performs deterministic naming, labelling,
and validation only. It adds no model, scaler, imputer, learned thresholds, or
target-derived predictor. The target is retained for later outcomes and must be
excluded from predictive features if modelling is added.

## Validation failures and reruns

Unrecognised schemas/codes, missing values, duplicate IDs, nonbinary targets,
fractional numeric values, nonpositive limits, and negative payments stop the
pipeline for inspection. Ages outside 18-100 also trigger inspection; that range
is a project guardrail, not a claim about UCI's inclusion criteria.

On failure, read `reports/data_quality.json`. The summary is marked failed, and
existing CSVs may be left over from a prior run. Use them only after a successful
rerun; this is deliberately not a multi-file transactional publishing system.
Raw originals are never changed by cleaning. Correct the cause rather than
bypassing validation or manually editing the raw files.

In-memory regression checks deliberately corrupt copies of real rows to verify
that invalid inputs are rejected. They do not change the source or export fake
customers. Run them after the dataset is available:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Interview explanation

"I downloaded the original UCI workbook, retained its bytes and checksum, and
validated it before cleaning. It had no missing values or duplicate customer
IDs, so I did not impute or remove customers. I kept negative bills and
undocumented codes with explicit flags because I could not justify changing
their meaning. I reconciled every original value and the exported CSV. The
clean file is still one row per customer, so the default rate uses 30,000
customers as its denominator rather than six months of repayment records."

The observed default rate is 6,636 / 30,000 = 22.12%. This describes the source
sample, not Finnable customers or a causal relationship. Collections actions
and their effectiveness are not measured here.

The next stage will create SQLite `customers`, `monthly_repayments`, and
`default_outcomes` tables, with validated keys and joins. None is created in
stage 2, and no Power BI dashboard is claimed.
