param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$checkOnlyRequested = $CheckOnly.IsPresent -or (
    [Environment]::GetCommandLineArgs() -contains "-CheckOnly"
) -or ($env:IMAGE3D_CHECK_ONLY -eq "1")

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$fixDir = Join-Path $projectRoot "fix"
$configPath = Join-Path $fixDir "config.json"
$appPath = Join-Path $fixDir "desktop_3d_generator.py"

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "找不到配置文件：$configPath"
}
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "找不到程序入口：$appPath"
}

function Add-PythonCandidate {
    param([System.Collections.Generic.List[string]]$List, [string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    try {
        $fullPath = [IO.Path]::GetFullPath(
            [Environment]::ExpandEnvironmentVariables($Path)
        )
    }
    catch {
        return
    }
    if (-not $List.Contains($fullPath)) {
        $List.Add($fullPath)
    }
}

function Test-AppPython {
    param([string]$PythonPath)
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $false
    }
    & $PythonPath -B -c "import tkinter, PIL, torch" 2>$null
    return $LASTEXITCODE -eq 0
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
$candidates = [System.Collections.Generic.List[string]]::new()

if ($env:IMAGE3D_TRIPOSR_PYTHON) {
    Add-PythonCandidate $candidates $env:IMAGE3D_TRIPOSR_PYTHON
}

$configuredPython = [string]$config.paths.triposr_python
if (
    $configuredPython -and
    $configuredPython -notin @("auto", "detect")
) {
    $expanded = [Environment]::ExpandEnvironmentVariables($configuredPython)
    if (-not [IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path $fixDir $expanded
    }
    Add-PythonCandidate $candidates $expanded
}

Add-PythonCandidate $candidates (Join-Path $projectRoot ".venv\Scripts\python.exe")
Add-PythonCandidate $candidates (Join-Path $projectRoot "runtime\triposr\python.exe")

if ($env:CONDA_PREFIX) {
    Add-PythonCandidate $candidates (Join-Path $env:CONDA_PREFIX "python.exe")
}

$condaCommand = Get-Command conda -ErrorAction SilentlyContinue
if ($condaCommand) {
    try {
        $envList = (& $condaCommand.Source env list --json 2>$null) |
            ConvertFrom-Json
        $orderedEnvs = @($envList.envs) | Sort-Object {
            if ((Split-Path $_ -Leaf) -ieq "triposr") { 0 } else { 1 }
        }
        foreach ($environment in $orderedEnvs) {
            Add-PythonCandidate $candidates (Join-Path $environment "python.exe")
        }
    }
    catch {
        # Conda is optional; continue with PATH candidates.
    }
}

foreach ($commandName in @("python.exe", "python")) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($command) {
        Add-PythonCandidate $candidates $command.Source
    }
}

$pythonPath = $null
foreach ($candidate in $candidates) {
    if (Test-AppPython $candidate) {
        $pythonPath = $candidate
        break
    }
}

if (-not $pythonPath) {
    throw (
        "没有找到可运行本项目的 Python。`n" +
        "程序已自动检查：项目 .venv、runtime\triposr、当前 Conda 环境、" +
        "名为 triposr 的 Conda 环境和系统 PATH。`n" +
        "请先安装项目依赖，或设置环境变量 IMAGE3D_TRIPOSR_PYTHON。"
    )
}

$env:IMAGE3D_CONFIG = $configPath
$env:IMAGE3D_TRIPOSR_PYTHON = $pythonPath
$env:PYTHONPATH = (Join-Path $projectRoot "TripoSR-main")

if ($checkOnlyRequested) {
    Write-Host "启动检查通过"
    Write-Host "项目目录：$projectRoot"
    Write-Host "Python：$pythonPath"
    Write-Host "程序入口：$appPath"
    $checkCode = (
        "import sys; " +
        "sys.path.insert(0, r'$fixDir'); " +
        "from config_loader import get_path; " +
        "keys=('triposr_python','triposr_dir','blender_exe','output_root','work_root'); " +
        "[print(f'{key}: {get_path(key)}') for key in keys]"
    )
    & $pythonPath -B -c $checkCode
    exit $LASTEXITCODE
}

& $pythonPath -B $appPath
if ($LASTEXITCODE -ne 0) {
    throw "程序退出代码：$LASTEXITCODE"
}
