# Execute a read-only DAX query against a Power BI Desktop model already open locally.
# Find the engine PID with Get-Process msmdsrv, then its port with netstat -ano -p tcp.
param(
    [Parameter(Mandatory=$true)][int]$Port,
    [Parameter(Mandatory=$true)][string]$QueryFile,
    [Parameter(Mandatory=$true)][string]$OutputFile
)

$ErrorActionPreference = "Stop"
$pbiLibrary = "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.AdomdClient.dll"
if (-not (Test-Path -LiteralPath $pbiLibrary)) { throw "Install Power BI Desktop first." }
[System.Reflection.Assembly]::LoadFrom($pbiLibrary) | Out-Null
$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection
$connection.ConnectionString = "Data Source=localhost:$Port;Application Name=Credit Risk Portfolio Validation"
$reader = $null
try {
    $connection.Open()
    $command = $connection.CreateCommand()
    $command.CommandText = Get-Content -LiteralPath $QueryFile -Raw
    $command.CommandTimeout = 120
    $reader = $command.ExecuteReader()
    $resultRows = @()
    while ($reader.Read()) {
        $row = [ordered]@{}
        for ($columnIndex = 0; $columnIndex -lt $reader.FieldCount; $columnIndex++) {
            $value = $reader.GetValue($columnIndex)
            if ($value -is [DBNull]) { $value = $null }
            $row[$reader.GetName($columnIndex)] = $value
        }
        $resultRows += [pscustomobject]$row
    }
    $result = [ordered]@{
        query_file = (Resolve-Path -LiteralPath $QueryFile).Path
        engine = "Power BI Desktop local Analysis Services / ADOMD.NET"
        queried_at_utc = [DateTime]::UtcNow.ToString("o")
        rows = @($resultRows)
    }
    $json = $result | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($OutputFile, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "Queried $($resultRows.Count) rows from the actual Power BI model. Results: $OutputFile"
}
finally {
    if ($null -ne $reader) { $reader.Dispose() }
    $connection.Dispose()
}
