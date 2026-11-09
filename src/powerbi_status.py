"""Report Desktop validation only when its saved evidence still matches the files."""

import hashlib
import json

from .download_data import PROJECT_ROOT


def current_status():
    binary = PROJECT_ROOT / "powerbi" / "Credit_Risk_Repayment_Analytics.pbix"
    evidence = PROJECT_ROOT / "reports" / "powerbi_runtime_validation.json"
    result = {"powerbi_dashboard_created": binary.is_file(), "powerbi_runtime_verified": False}
    if not binary.is_file() or not evidence.is_file():
        return result
    report = json.loads(evidence.read_text(encoding="utf-8"))
    files = report.get("file_sha256", {})
    result["powerbi_runtime_verified"] = bool(files) and report.get("status") == "passed" and all(
        (PROJECT_ROOT / relative).is_file()
        and hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() == expected
        for relative, expected in files.items()
    ) and "powerbi/Credit_Risk_Repayment_Analytics.pbix" in files
    return result
