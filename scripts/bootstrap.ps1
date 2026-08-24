[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Corpus
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SkillRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $SkillRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
$Requirements = Join-Path $SkillRoot "requirements.txt"
$CorpusRequirements = Join-Path $SkillRoot "requirements-corpus.txt"

function Test-FetcherDependencies {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $false
    }

    try {
        & $PythonPath -c "import openpyxl, pypdf" 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Test-CorpusDependencies {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return $false
    }

    try {
        & $PythonPath -c "import docling, docling_core, pypdfium2, scipy; from docling.document_converter import DocumentConverter" 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

$BaseReady = Test-FetcherDependencies -PythonPath $VenvPython
$CorpusReady = if ($Corpus) { Test-CorpusDependencies -PythonPath $VenvPython } else { $false }
if ($BaseReady -and (-not $Corpus -or $CorpusReady) -and -not $Force) {
    Write-Host "paper-fulltext-fetcher environment is ready."
    if ($Corpus) {
        Write-Host "Optional corpus environment is ready."
    }
    Write-Host "Run: & .\scripts\run.ps1 self-test"
    exit 0
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        & $PyLauncher.Source -3 -m venv $VenvRoot
    }
    else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $PythonCommand) {
            throw "Python 3.11 or newer was not found. Install Python, then rerun bootstrap.ps1."
        }
        & $PythonCommand.Source -m venv $VenvRoot
    }

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Failed to create the private Python environment."
    }
}

$VersionCheck = & $VenvPython -c "import sys; print(int(sys.version_info >= (3, 11)))"
if ($LASTEXITCODE -ne 0 -or $VersionCheck.Trim() -ne "1") {
    throw "paper-fulltext-fetcher requires Python 3.11 or newer."
}

if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "requirements.txt is missing from the Skill directory."
}

& $VenvPython -m pip install --disable-pip-version-check -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Check network access and rerun bootstrap.ps1."
}

if ($Corpus) {
    if (-not (Test-Path -LiteralPath $CorpusRequirements -PathType Leaf)) {
        throw "requirements-corpus.txt is missing from the Skill directory."
    }
    & $VenvPython -m pip install --disable-pip-version-check -r $CorpusRequirements
    if ($LASTEXITCODE -ne 0) {
        throw "Optional corpus dependency installation failed. Check network access and rerun bootstrap.ps1 -Corpus."
    }
}

if (-not (Test-FetcherDependencies -PythonPath $VenvPython)) {
    throw "The private environment was created, but required packages are unavailable."
}

if ($Corpus -and -not (Test-CorpusDependencies -PythonPath $VenvPython)) {
    throw "The private environment was created, but optional corpus dependencies are unavailable."
}

Write-Host "paper-fulltext-fetcher environment is ready."
if ($Corpus) {
    Write-Host "Optional corpus environment is ready."
}
Write-Host "Run: & .\scripts\run.ps1 self-test"
