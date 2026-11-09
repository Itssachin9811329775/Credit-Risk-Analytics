"""Check stage-1 prerequisites without downloading or analysing customer data."""

import importlib
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
from datetime import datetime, timezone


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PACKAGES = ("numpy", "pandas", "matplotlib", "seaborn", "xlrd")
PROJECT_FOLDERS = (
    "data/raw",
    "data/processed",
    "data/exports",
    "database",
    "sql",
    "src",
    "reports/figures",
    "docs",
    "powerbi",
)


def main():
    # Keep Matplotlib's font cache inside the project, including on locked-down PCs.
    cache_path = PROJECT_ROOT / ".cache" / "matplotlib"
    cache_path.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_path)

    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "packages": {},
        "checks": [],
    }

    def record(name, passed, detail):
        report["checks"].append({"name": name, "passed": passed, "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    record("Python version", sys.version_info >= (3, 11), report["python"])
    expected_venv = (PROJECT_ROOT / ".venv").resolve()
    in_project_venv = sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == expected_venv
    record("Project virtual environment", in_project_venv, sys.executable)

    modules = {}
    for name in REQUIRED_PACKAGES:
        try:
            modules[name] = importlib.import_module(name)
            version = str(modules[name].__version__)
            report["packages"][name] = version
            record(f"Import {name}", True, version)
        except Exception as exc:
            record(f"Import {name}", False, str(exc))

    try:
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            # Constants check SQL capabilities only; these are not customer records.
            result = connection.execute(
                """
                WITH capability_check AS (SELECT 1 AS value)
                SELECT CASE WHEN value = 1 THEN 'ok' END,
                       ROW_NUMBER() OVER (ORDER BY value)
                FROM capability_check
                """
            ).fetchone()
            record("SQLite CTE, CASE, window function", result == ("ok", 1), report["sqlite"])
            record("SQLite foreign-key support", foreign_keys == 1, "Enabled on the temporary connection")
        finally:
            connection.close()
    except Exception as exc:
        record("SQLite capabilities", False, str(exc))

    if "matplotlib" in modules and "seaborn" in modules:
        try:
            modules["matplotlib"].use("Agg", force=True)
            pyplot = importlib.import_module("matplotlib.pyplot")
            modules["seaborn"].set_theme(style="whitegrid")
            figure, axis = pyplot.subplots(figsize=(3, 2))
            try:
                axis.set_title("Environment check - no data")
                with io.BytesIO() as buffer:
                    figure.savefig(buffer, format="png")
                    rendered = buffer.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
                record("PNG rendering", rendered, "Blank figure rendered in memory; no analysis chart created")
            finally:
                pyplot.close(figure)
        except Exception as exc:
            record("PNG rendering", False, str(exc))
    else:
        record("PNG rendering", False, "Matplotlib and Seaborn imports are required")

    missing_folders = [name for name in PROJECT_FOLDERS if not (PROJECT_ROOT / name).is_dir()]
    record("Project folders", not missing_folders, ", ".join(missing_folders) or "All present")

    passed = all(check["passed"] for check in report["checks"])
    report["status"] = "passed" if passed else "failed"
    report_path = PROJECT_ROOT / "reports" / "environment_check.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nEnvironment report: {report_path}")
    print("Stage 1 checks passed." if passed else "Fix the failed checks before stage 2.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
