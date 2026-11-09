# Install Microsoft's signed Power BI Desktop package for local report validation.
# This is separate from the Python setup because it installs a Windows application.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$installerDirectory = Join-Path $projectRoot ".cache\installers"
$installerPath = Join-Path $installerDirectory "PBIDesktopSetup_x64.exe"
$downloadUrl = "https://download.microsoft.com/download/8/8/0/880bca75-79dd-466a-927d-1abf1f5454b0/PBIDesktopSetup_x64.exe"
$desktopPath = "C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe"

if (Test-Path -LiteralPath $desktopPath) {
    Write-Output "Power BI Desktop is already installed: $desktopPath"
    exit 0
}
New-Item -ItemType Directory -Path $installerDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $installerPath)) {
    Write-Output "Downloading Power BI Desktop from the official Microsoft Download Center..."
    & curl.exe --fail --location --retry 2 --output $installerPath $downloadUrl
    if ($LASTEXITCODE -ne 0) { throw "The Microsoft installer download failed." }
}
$signature = Get-AuthenticodeSignature -LiteralPath $installerPath
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
    throw "Installer signature is not a valid Microsoft signature; installation stopped."
}
Write-Output "Verified Microsoft signature. Installing Power BI Desktop..."
$installation = Start-Process -FilePath $installerPath -ArgumentList @('-quiet', '-norestart', 'ACCEPT_EULA=1') -Wait -PassThru -WindowStyle Hidden
if ($installation.ExitCode -notin @(0, 3010)) {
    throw "Power BI installation returned exit code $($installation.ExitCode)."
}
if (-not (Test-Path -LiteralPath $desktopPath)) { throw "Installer ended, but PBIDesktop.exe was not found at the expected path." }
Write-Output "Installed Power BI Desktop: $desktopPath"
if ($installation.ExitCode -eq 3010) { Write-Output "The installer reports a restart may be required; no restart was performed." }
