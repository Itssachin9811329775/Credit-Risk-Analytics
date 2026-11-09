"""Download the official UCI archive once, retaining source bytes and provenance."""

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients"
DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/350/default%2Bof%2Bcredit%2Bcard%2Bclients.zip"
ARCHIVE_PATH = RAW_DIR / "uci_350_original.zip"
WORKBOOK_NAME = "default of credit card clients.xls"
WORKBOOK_PATH = RAW_DIR / WORKBOOK_NAME
MANIFEST_PATH = RAW_DIR / "source_manifest.json"


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def verify_cached_download():
    """Reject changed or incomplete raw files instead of silently replacing them."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["dataset_id"] != 350 or manifest["download_url"] != DOWNLOAD_URL:
        raise ValueError("Raw manifest does not describe the expected UCI source.")
    for path in (ARCHIVE_PATH, WORKBOOK_PATH):
        content = path.read_bytes()
        expected = manifest["files"][path.name]
        if sha256(content) != expected["sha256"] or len(content) != expected["size_bytes"]:
            raise ValueError(f"Raw file has changed since download: {path}")
    # Verify that the workbook on disk still matches the preserved archive member.
    with ZipFile(ARCHIVE_PATH) as archive:
        if sha256(archive.read(WORKBOOK_NAME)) != manifest["files"][WORKBOOK_NAME]["sha256"]:
            raise ValueError("Workbook and original archive disagree.")
    return manifest


def ensure_dataset(offline=False):
    """Return a verified workbook path. Existing valid downloads need no network."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if MANIFEST_PATH.exists():
        verify_cached_download()
        print("Using original UCI files; both SHA-256 checksums match.")
        return WORKBOOK_PATH
    if ARCHIVE_PATH.exists() or WORKBOOK_PATH.exists():
        raise ValueError("Raw files exist without a manifest. Inspect them before proceeding; no raw files were overwritten.")
    if offline:
        raise FileNotFoundError("No verified local download. Run without --offline once to download from UCI.")

    print(f"Downloading UCI dataset 350 from {DOWNLOAD_URL}", flush=True)
    request = Request(DOWNLOAD_URL, headers={"User-Agent": "CreditRiskPortfolio/1.0"})
    with urlopen(request, timeout=30) as response:
        archive_bytes = response.read(20_000_001)
        resolved_url = response.geturl()
    if len(archive_bytes) > 20_000_000:
        raise ValueError("Unexpectedly large archive; inspect the source before continuing.")
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        if archive.namelist().count(WORKBOOK_NAME) != 1:
            raise ValueError("Expected exactly one original UCI XLS workbook in the archive.")
        if archive.getinfo(WORKBOOK_NAME).file_size > 20_000_000:
            raise ValueError("Unexpectedly large workbook.")
        # Read only the named member; never extract arbitrary archive paths.
        workbook_bytes = archive.read(WORKBOOK_NAME)
    if not workbook_bytes.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise ValueError("Downloaded workbook is not a legacy Excel file.")

    manifest = {
        "dataset_id": 350,
        "dataset_title": "Default of Credit Card Clients",
        "source_page": SOURCE_PAGE,
        "download_url": DOWNLOAD_URL,
        "resolved_download_url": resolved_url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "doi": "10.24432/C55S3H",
        "license": "CC BY 4.0",
        "files": {
            ARCHIVE_PATH.name: {"sha256": sha256(archive_bytes), "size_bytes": len(archive_bytes)},
            WORKBOOK_NAME: {"sha256": sha256(workbook_bytes), "size_bytes": len(workbook_bytes)},
        },
    }
    # Exclusive creation protects existing originals. A partial write is not reused.
    with ARCHIVE_PATH.open("xb") as output:
        output.write(archive_bytes)
    with WORKBOOK_PATH.open("xb") as output:
        output.write(workbook_bytes)
    with MANIFEST_PATH.open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
        output.write("\n")
    verify_cached_download()
    print(f"Preserved original archive, workbook, and source manifest in {RAW_DIR}")
    return WORKBOOK_PATH


if __name__ == "__main__":
    ensure_dataset()
