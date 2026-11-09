# Stage 3: model and validate the SQLite database

Stage 3 builds `database/credit_risk.sqlite` from the verified stage-2 CSV.
The completed build contains 30,000 customer rows, 180,000 monthly repayment
rows, and 30,000 outcome rows. Every stored value was reconciled to the cleaned
source. The generated [validation summary](../reports/stage_03_summary.md) and
[JSON report](../reports/database_validation.json) contain the latest results.

## Run it in Windows PowerShell

After completing stages 1 and 2, run:

```powershell
Set-Location 'C:\Users\Sachin\OneDrive\Documents\Desktop\DS_Project'
.\.venv\Scripts\python.exe -m src.build_database
```

No download or additional package is needed. SQLite is included with Python.
The command creates a candidate database, validates it, and then publishes it
as `database/credit_risk.sqlite`. Rerunning rebuilds this generated artifact;
the raw workbook and cleaned CSV remain unchanged.

To check the existing database without rebuilding it:

```powershell
.\.venv\Scripts\python.exe -m src.build_database --validate-only
```

This opens the database read-only and refreshes the validation reports. It
requires an existing database and the verified stage-2 source files; it does
not silently create a missing database. Success prints `Stage 3 passed`, the
number of checks, and the three row counts.

## Understand what one row represents

The **grain** of a table is the meaning of one row. State it before writing a
query or choosing a denominator.

- **`customers`: one row per customer.** `customer_id` is the primary key.
  The table stores the credit limit in NTD, demographic codes and labels, age,
  and the two source-quality flags. Flags are stored as integers 0 or 1.
- **`monthly_repayments`: one row per customer per month.** The composite
  primary key is `(customer_id, month)`: neither column alone identifies a
  row. It stores the original repayment code, bill amount, and payment amount.
  `customer_id` is also a foreign key referencing `customers`.
- **`default_outcomes`: one future outcome per customer.** `customer_id` is
  both the primary key and a foreign key referencing `customers`.
  `default_next_month` is 0 or 1. There is no separate outcome for each of the
  six history months.

Each customer therefore has six repayment rows and one outcome row. The
primary keys prevent duplicates; the foreign keys prevent child records from
referencing absent customers. Foreign keys alone cannot ensure that every
customer has a complete history or an outcome. Separate coverage checks
establish those requirements.

## Why the schema is explicit

[sql/schema.sql](../sql/schema.sql) defines the tables before Python inserts
records. Explicit keys, `NOT NULL`, and `CHECK` constraints keep invalid values
from being loaded accidentally. For example, the database rejects duplicate
customer-month pairs, negative payment amounts, and outcomes outside 0/1.
Negative bills remain allowed because they occur in the source.

All three tables use `STRICT` typing, supported by SQLite 3.37.0 and later.
The builder checks this requirement. Integer columns reject values that cannot
be converted to an integer without loss; this does not mean that every
convertible text representation is rejected. See the
[SQLite STRICT documentation](https://www.sqlite.org/stricttables.html).

`WITHOUT ROWID` uses the declared primary key as the row identifier. It also
prevents SQLite from generating a customer ID when a NULL is supplied to an
integer primary key. IDs must come from the source. This is an integrity
choice here, not a measured performance claim. See
[SQLite's explanation](https://www.sqlite.org/withoutrowid.html).

Foreign-key enforcement is enabled on every connection before inserting data.
It is a connection setting, not a permanent switch stored in the database.
An external SQL editor must enable it on its own connection. See
[SQLite foreign-key support](https://www.sqlite.org/foreignkeys.html).

The monthly primary key supports looking up a customer's history. A separate
index on `(month, customer_id)` supports selecting a particular month.

## What the Python pipeline does

1. Require a successful stage-2 report, verify the raw-file checksums and source
   provenance, and confirm that the clean CSV's SHA-256 matches the stage-2
   report. Read those verified bytes into Pandas.
2. Split customer attributes and the target into their own tables. Reshape the
   six history periods into customer-month rows using the explicit stage-2
   mapping. September status comes from `PAY_0`; September bills and payments
   come from suffix 1. There is no source `PAY_1`.
3. Create the SQL schema in a separate candidate file. Insert all three tables
   using bound parameters inside one transaction. Failed inserts roll back.
4. Compare all database rows and values with the expected tables, ordered by
   their keys. Compare installed table, constraint, and index definitions with
   a fresh copy of `sql/schema.sql`, including during `--validate-only`.
   Check SQLite integrity, foreign keys, key definitions, month coverage,
   outcome coverage, and customer-level join totals.
5. Close the database connection before replacing the generated database on
   Windows. Record the input, schema, and database hashes in the JSON report.

The loader deliberately uses the explicit schema and parameterised inserts;
it does not use `to_sql(..., if_exists="replace")`, which would replace the
carefully defined tables and their constraints.

## Join without counting a customer six times

A direct join from customers to all monthly rows produces 180,000 rows.
Summing the repeated default flags gives 39,816 instead of 6,636 defaulting
customers. Customer credit limits are repeated too. They total 5,024,529,680
NTD at customer grain, not the 30,147,178,080 NTD produced by that direct join.
Credit limits are not outstanding balances.

`COUNT(DISTINCT customer_id)` repairs the customer count only. It does not
repair repeated credit limits or outcome sums. The default percentage happens
to remain 22.12% when every customer appears exactly six times, so a plausible
percentage alone does not prove the join is correct. Filtering monthly rows
can also change how many times different customers are counted.

Aggregate the monthly table to one row per customer first:

```sql
WITH monthly_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS history_months
    FROM monthly_repayments
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.credit_limit_ntd,
    m.history_months,
    d.default_next_month
FROM customers AS c
JOIN monthly_summary AS m ON m.customer_id = c.customer_id
JOIN default_outcomes AS d ON d.customer_id = c.customer_id;
```

This query returns one row per customer. Later customer-level repayment
features can be calculated inside the CTE before joining. Selecting one
specific month is another valid approach when answering a question about that
month; the composite key guarantees at most one record per customer then.

[sql/check_join_grain.sql](../sql/check_join_grain.sql) demonstrates the direct
join alongside the customer-only and aggregate-before-join alternatives. The
builder runs this diagnostic and reconciles its counts and totals. It is a
validation example, not one of the ten stage-4 business analyses.

## Preserve meaning while changing the storage layout

Repayment codes `-2` and `0` remain undocumented numeric codes, not NULL, on-time
statuses, or delinquency labels. Code `-1` is documented as paid duly; positive
codes represent recorded delay categories. The original codes remain available
for separate reporting. Unexplained education and marriage codes retain their
explicit undocumented labels.

Bill and payment amounts retain their original values and NTD units. A bill
statement is a monthly snapshot: summing all six statements is not a measure
of a customer's unique outstanding debt. Payments are recorded monthly
amounts; the file does not provide the contractual amounts due or collection
interventions needed to establish recovery effectiveness.

Keeping the target in `default_outcomes` makes its role clear. It must still
be excluded from predictors if modelling is added later. No outcome date or
monthly sequence of default events has been invented.

## Failures and reruns

If input verification or validation fails, read
`reports/database_validation.json`. The summary is marked failed. A database
left from an earlier successful build must not be treated as the current
validated output. Correct the cause and rerun validation or rebuild.

The builder preserves the existing database until the candidate has passed
validation. It also refuses to overwrite a database without this project's
application identifier or with an unexpected set of tables. Close external
database viewers if Windows prevents
replacing an open file. Correct input issues through the stage-2 pipeline;
do not manually patch the generated database to bypass checks.

If `sql/schema.sql` changes, rebuild before using `--validate-only`; validation
compares the installed definitions with that file.

## Regression checks

Run all completed-stage tests offline:

```powershell
.\.venv\Scripts\python.exe -W error -m unittest discover -s tests -v
```

All 24 tests passed: 12 for data preparation and 12 for SQLite. The database
tests cover invalid keys and values, missing constraints, independent source
month mappings, and changed values whose aggregate totals still match. They
also confirm that a failed build preserves the previously published database.
They use real source records in memory or temporary databases, without changing
the project's database or customer files.

The actual build passed 29 validation checks. A repeated build produced an
identical database file; read-only validation left its bytes unchanged. The raw
and processed source files also remained unchanged.

## Interview explanation

"I separated customer attributes, monthly repayment history, and the future
outcome because they have different grains. I used a customer-month primary
key and foreign keys, then reconciled every stored value and checked that all
customers had six months and one outcome. I demonstrated the sixfold inflation
from a direct monthly join and fixed it by aggregating before joining. That
keeps the customer denominator and monetary totals meaningful."

This remains historical Taiwanese credit-card data, not Finnable data.
Database integrity checks do not establish representativeness, causality, or
the effect of a collections strategy. Stage 4 will add the ten business SQL
analyses; exploratory charts, Power BI work, and optional modelling remain
later stages.
