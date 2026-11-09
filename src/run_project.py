r"""Run the complete portfolio pipeline from the project root.

Core: .\.venv\Scripts\python.exe -m src.run_project --offline
The optional modelling extension is not included in this core pipeline.
"""

import argparse
import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone

from .download_data import PROJECT_ROOT
from .powerbi_status import current_status


def run(offline=False):
    status = {"status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "core_complete": False, "powerbi_dashboard_created": False, "completed_stages": [],
              "optional_model": "not_included"}
    report_path = PROJECT_ROOT / "reports" / "project_status.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "check_environment.py")], check=True)
        status["completed_stages"].append(1)
        importlib.import_module("src.prepare_data").run(offline=offline)
        status["completed_stages"].append(2)
        for stage, module in ((3, "build_database"), (4, "run_sql_analysis"), (5, "explore_data"),
                              (6, "export_powerbi"), (7, "write_findings")):
            importlib.import_module(f"src.{module}").run()
            status["completed_stages"].append(stage)
        status["core_complete"] = True
        status["status"] = "passed"
    except Exception as exc:
        status["status"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        status.update(current_status())
        status["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print("Core project complete. Power BI file and runtime verification status:")
    print(json.dumps(current_status(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use the already-downloaded source without network")
    arguments = parser.parse_args()
    run(offline=arguments.offline)
