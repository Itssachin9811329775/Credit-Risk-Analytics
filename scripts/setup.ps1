# Run from PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
# This sets up stage 1 only. It never downloads the dataset.
[CmdletBinding()]
param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"
$lockedRequirements = Join-Path $projectRoot "requirements-lock.txt"

try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (Test-Path -LiteralPath $venvDirectory) {
            throw ".venv exists but has no Windows Python executable. Inspect it before retrying; setup will not overwrite it."
        }
        Write-Host "Creating project virtual environment..."
        & $PythonCommand -m venv $venvDirectory
        if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
    }

    & $venvPython -c "import sys; print('Python:', sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Use Python 3.11 or newer. This project is being verified on Python 3.14." }

    $installFrom = $requirements
    if (Test-Path -LiteralPath $lockedRequirements) {
        $installFrom = $lockedRequirements
    }
    Write-Host "Installing dependencies from $installFrom"
    & $venvPython -m pip install --disable-pip-version-check --only-binary=:all: -r $installFrom
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check the pip error above and rerun setup after fixing it." }

    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip found incompatible dependencies." }

    & $venvPython (Join-Path $PSScriptRoot "check_environment.py")
    if ($LASTEXITCODE -ne 0) { throw "Environment verification failed. See reports/environment_check.json." }

    if (-not (Test-Path -LiteralPath $lockedRequirements)) {
        $installedPackages = & $venvPython -m pip freeze
        if ($LASTEXITCODE -ne 0) { throw "Could not capture installed package versions." }
        $verifiedPythonVersion = & $venvPython -c "import platform; print(platform.python_version())"
        if ($LASTEXITCODE -ne 0) { throw "Could not capture the Python version." }
        $lockContents = @(
            "# Exact packages from the verified project environment."
            "# Verified on Windows with Python $verifiedPythonVersion; regenerate deliberately when changing dependencies."
        ) + $installedPackages
        $lockContents | Set-Content -LiteralPath $lockedRequirements -Encoding ASCII
    }

    Write-Host "Stage 1 complete. No dataset has been downloaded by setup."
    Write-Host "Recheck with: .\.venv\Scripts\python.exe .\scripts\check_environment.py"
    exit 0
}
catch {
    Write-Host "Setup failed: $_" -ForegroundColor Red
    exit 1
}
