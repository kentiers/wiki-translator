# PowerShell launcher for Wiki Translator Suite

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$mainPy = Join-Path $scriptDir "main.py"

# 1. Try uv from PATH
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run python $mainPy @args
    exit $LASTEXITCODE
}

# 2. Try uv from default user local bin
$userUv = "$env:USERPROFILE\.local\bin\uv.exe"
if (Test-Path $userUv) {
    & $userUv run python $mainPy @args
    exit $LASTEXITCODE
}

# 3. Try uv-managed Python installations in AppData\Roaming\uv\python
$uvPythons = Get-ChildItem -Path "$env:APPDATA\uv\python\cpython-*\python.exe" -ErrorAction SilentlyContinue
if ($uvPythons) {
    & $uvPythons[0].FullName $mainPy @args
    exit $LASTEXITCODE
}

# 4. Try standard Python installations in LocalAppData\Programs\Python
$localPythons = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue
if ($localPythons) {
    & $localPythons[0].FullName $mainPy @args
    exit $LASTEXITCODE
}

# 5. Fallback to python in PATH
& python $mainPy @args
exit $LASTEXITCODE
