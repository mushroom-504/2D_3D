param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixDir = Join-Path $projectRoot "fix"
$configPath = Join-Path $fixDir "config.json"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Config file not found: $configPath"
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$pythonValue = [Environment]::ExpandEnvironmentVariables(
    [string]$config.paths.triposr_python
)
if (-not [IO.Path]::IsPathRooted($pythonValue)) {
    $pythonValue = Join-Path $fixDir $pythonValue
}
$pythonPath = [IO.Path]::GetFullPath($pythonValue)
$appPath = Join-Path $fixDir "desktop_3d_generator.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "TripoSR Python not found: $pythonPath. Update paths.triposr_python in fix\config.json."
}
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Application entry point not found: $appPath"
}

if ($CheckOnly) {
    Write-Host "Launcher check OK"
    Write-Host "Python: $pythonPath"
    Write-Host "App: $appPath"
    exit 0
}

& $pythonPath $appPath
if ($LASTEXITCODE -ne 0) {
    throw "Application exit code: $LASTEXITCODE"
}
