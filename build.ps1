param(
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not $PythonExecutable) {
    $hueInstalledPython = Get-ChildItem -LiteralPath "$env:LOCALAPPDATA\Programs\Python" -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "Python3\d+\\python\.exe$" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($hueInstalledPython) {
        $PythonExecutable = $hueInstalledPython.FullName
    } else {
        $huePythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($huePythonCommand) {
            $PythonExecutable = $huePythonCommand.Source
        }
    }
}

if (-not $PythonExecutable -or -not (Test-Path -LiteralPath $PythonExecutable)) {
    throw "A standard Python 3.10+ installation was not found. Pass its path with -PythonExecutable."
}

& $PythonExecutable -c "import tkinter"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python does not include Tkinter: $PythonExecutable"
}

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    & $PythonExecutable -m venv .venv
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
& $python -c "import tkinter"
if ($LASTEXITCODE -ne 0) {
    throw "The existing .venv does not include Tkinter. Recreate it with a standard Python installation."
}
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[build]"
& $python scripts\create_icon.py
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name HueLightPerfMon `
    --icon assets\huelightperfmon.ico `
    --paths src `
    src\huelightperfmon\__main__.py

Write-Host ""
Write-Host "Built: $projectRoot\dist\HueLightPerfMon.exe"
