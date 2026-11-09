# Dataset source and attribution

Selected dataset: **Default of Credit Card Clients**, UCI dataset ID **350**.

- [Official dataset page](https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients)
- [Persistent DOI](https://doi.org/10.24432/C55S3H)
- Creator: I-Cheng Yeh.
- Licence listed by UCI: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

UCI's citation: Yeh, I. (2009). *Default of Credit Card Clients* [Dataset].
UCI Machine Learning Repository. https://doi.org/10.24432/C55S3H.

The official description concerns Taiwanese credit-card clients and monthly
repayment history from April through September 2005. Monetary variables use
New Taiwan dollars. The listed file is `default of credit card clients.xls`;
the project includes `xlrd` to read this legacy Excel format.

These are source descriptions, not results calculated in this project. This is
not Finnable data, and the project has no affiliation with or internal data from
Finnable. Interview preparation is the reason for choosing the topic.

Stage 2 downloaded the archive from the official page's download link:
[UCI archive](https://archive.ics.uci.edu/static/public/350/default%2Bof%2Bcredit%2Bcard%2Bclients.zip).
The original archive and workbook are preserved under `data/raw/`.
`data/raw/source_manifest.json` records the URL, resolved URL, UTC retrieval time,
byte sizes, and SHA-256 checksums; the same metadata is embedded in
[`reports/data_quality.json`](../reports/data_quality.json).

The workbook SHA-256 is
`30c6be3abd8dcfd3e6096c828bad8c2f011238620f5369220bd60cfc82700933`.
The archive SHA-256 is
`56c885f84457f6680f8438f02bfcdac9579323d8a94465ee5f26e32baa727602`.
These hashes record the downloaded bytes; they are not independently published
checksums supplied by UCI.

The actual workbook has one sheet, `Data`. Its second Excel row contains the
column headers (`header=1` in Pandas); the first row holds X/Y variable markers.
The observed data contains 30,000 rows and 25 columns, including ID and target.
Read [the stage 2 guide](stage_02_data_preparation.md) for transformations and
[the generated quality summary](../reports/stage_02_summary.md) for validation results.

The study period, population, and credit product limit how far findings can be
generalised. Relationships observed here do not establish causal effects or
show the impact of collections interventions.
