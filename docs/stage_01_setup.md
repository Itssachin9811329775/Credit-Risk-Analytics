# Stage 1: environment and project setup

The purpose of this stage is to establish a reproducible place to work before
loading customer data.

## Environment inspected

The workspace was empty when inspected. Windows PowerShell 5.1, Python 3.14.2,
pip 25.3, and SQLite 3.50.4 were available. Python was found at
`C:\Python314\python.exe`. Git was also available. No existing project files
needed to be changed.

The project uses a local `.venv` so its packages do not interfere with other
Python projects. The setup requires Python 3.11 or newer; the environment being
verified here is Python 3.14 on Windows. The generated environment report records
the actual interpreter and package versions each time you run it.

Verification completed successfully: all 11 environment checks passed and
`pip check` found no broken requirements. Installed direct dependencies are
NumPy 2.5.4, Pandas 2.3.3, Matplotlib 3.11.2, Seaborn 0.13.2, and xlrd 2.0.2.
Exact transitive dependencies are captured in `requirements-lock.txt`.

The first installation attempt was blocked by the execution sandbox's network
policy. Rerunning with network approval succeeded; no package compatibility
error remained.

## Packages and their jobs

- **Pandas:** inspect, clean, reshape, validate, and export tabular data.
- **NumPy:** numerical operations and a foundation for the analysis libraries.
- **Matplotlib:** control chart labels, layout, and image exports.
- **Seaborn:** create statistical plots using Matplotlib.
- **xlrd:** read the `.xls` file supplied by UCI.

SQLite is accessed through Python's built-in `sqlite3` module. Downloads can use
the built-in `urllib` module, and ZIP files can use `zipfile`. Neither a database
server nor an extra SQLite pip package is needed. Power BI Desktop is a separate
application; this setup does not install it or verify its availability. Its setup
will be addressed at stage 6. scikit-learn is deferred until the core analysis is
complete.

`requirements.txt` declares the five direct dependencies. The Pandas lower bound
reflects [Python 3.14 support introduced in Pandas 2.3.3](https://pandas.pydata.org/pandas-docs/version/2.3.3/whatsnew/v2.3.3.html).
We keep Pandas within its 2.x series for this project's initial implementation.
The setup requests binary wheels to avoid requiring a C/C++ compiler.

`requirements-lock.txt` captures all installed package versions after the first
successful check. Subsequent setup runs use it for repeatability. Keep both
requirements files with the project; review them together if dependencies are
deliberately changed. The lock is tested for this Windows/Python environment,
not a guarantee for every operating system or future Python version.

## Commands

Run from Windows PowerShell:

```powershell
Set-Location 'C:\Users\Sachin\OneDrive\Documents\Desktop\DS_Project'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script reuses a valid existing `.venv` and stops if a command fails. It does
not delete an existing environment. The execution-policy argument applies only
to the child PowerShell process.

To run the checks again without installing packages:

```powershell
.\.venv\Scripts\python.exe .\scripts\check_environment.py
```

To check installed package requirements separately:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

## What verification covers

The setup runs `pip check` for dependency consistency. The Python checker
verifies the interpreter, use of this project's `.venv`, all five package
imports, the required folders, and an in-memory SQLite query using CTEs, CASE,
and a window function. It also checks that SQLite can enable foreign-key
enforcement. Every later database connection must enable that setting again.

Matplotlib renders a blank figure in memory with Seaborn styling to confirm PNG
export works. SQL constants and this blank figure are environment checks, not
synthetic customer data or analytical findings. No customer database or chart
file is created. Package checks do not validate the source data; that is stage 2.

Results are printed as `[PASS]` or `[FAIL]` and written to
`reports/environment_check.json`. The checker exits with a nonzero status when
a check fails. Matplotlib's local font cache is stored under `.cache/`.

## Common fixes

- If `python` cannot be found, pass a full interpreter path:
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -PythonCommand 'C:\Python314\python.exe'`.
- If installation reports network, proxy, or access errors, resolve the network
  restriction and rerun the same setup command. Do not disable certificate checks.
- If a wheel cannot be found, check that the interpreter is a supported Windows
  Python and that the package index is reachable; do not assume compilation is
  required merely because pip could not reach the index.
- If the project-environment check fails, run the exact `.venv` Python command
  above instead of the global `python` command.
- If `.venv` exists but is incomplete, inspect its contents before recreating it.
  The script intentionally stops instead of overwriting an unknown directory.

## How to explain this stage in an interview

"I isolated the project dependencies and recorded the versions so the analysis
can be rerun. I separated original data, cleaned data, SQL, charts, and dashboard
exports to keep the workflow traceable. Before analysis, I checked the tools and
defined the intended grain: a customer row versus a customer-month row. That
helps prevent duplicated customer totals when repayment history is joined."

Stage 2 will download and inspect the actual UCI dataset. No default rate,
segment result, model score, or dashboard completion is claimed at this stage.
