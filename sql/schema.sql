-- UCI 350 only. This script is applied to a NEW candidate database.
-- SQLite >= 3.37 is needed for STRICT. Enable foreign keys before inserting.
PRAGMA foreign_keys = ON;

-- Grain: one row per customer. Amounts are whole New Taiwan dollars (NTD).
CREATE TABLE customers (
    customer_id INTEGER NOT NULL PRIMARY KEY CHECK (customer_id > 0),
    credit_limit_ntd INTEGER NOT NULL CHECK (credit_limit_ntd > 0),
    sex_code INTEGER NOT NULL CHECK (sex_code IN (1, 2)),
    education_code INTEGER NOT NULL CHECK (education_code BETWEEN 0 AND 6),
    marriage_code INTEGER NOT NULL CHECK (marriage_code BETWEEN 0 AND 3),
    age INTEGER NOT NULL CHECK (age BETWEEN 18 AND 100),
    sex_label TEXT NOT NULL,
    education_label TEXT NOT NULL,
    marriage_label TEXT NOT NULL,
    has_negative_bill INTEGER NOT NULL CHECK (has_negative_bill IN (0, 1)),
    has_undocumented_repayment_code INTEGER NOT NULL
        CHECK (has_undocumented_repayment_code IN (0, 1))
) STRICT, WITHOUT ROWID;

-- Grain: one row per customer per month. There are six history months.
CREATE TABLE monthly_repayments (
    customer_id INTEGER NOT NULL,
    month TEXT NOT NULL CHECK (month IN (
        '2005-04', '2005-05', '2005-06', '2005-07', '2005-08', '2005-09'
    )),
    -- Preserve -2 and 0 as undocumented codes, not on-time/delinquent labels.
    repayment_status INTEGER NOT NULL CHECK (repayment_status BETWEEN -2 AND 9),
    -- Negative bills exist in the source and must remain valid.
    bill_amount_ntd INTEGER NOT NULL,
    payment_amount_ntd INTEGER NOT NULL CHECK (payment_amount_ntd >= 0),
    PRIMARY KEY (customer_id, month),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT, WITHOUT ROWID;

-- The primary key supports per-customer history; this index supports month filters.
CREATE INDEX idx_monthly_repayments_month ON monthly_repayments(month, customer_id);

-- Grain: one NEXT-month outcome per customer, not one outcome per history month.
CREATE TABLE default_outcomes (
    customer_id INTEGER NOT NULL PRIMARY KEY,
    default_next_month INTEGER NOT NULL CHECK (default_next_month IN (0, 1)),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT, WITHOUT ROWID;
