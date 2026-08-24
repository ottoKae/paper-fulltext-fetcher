[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$FetcherArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SkillRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $SkillRoot ".venv\Scripts\python.exe"
$FetcherScript = Join-Path $PSScriptRoot "paper_fulltext_fetcher.py"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "The private Python environment is missing. Run .\scripts\bootstrap.ps1 first."
}

if (-not (Test-Path -LiteralPath $FetcherScript -PathType Leaf)) {
    throw "paper_fulltext_fetcher.py is missing from the Skill scripts directory."
}

if ($FetcherArguments.Count -eq 0) {
    $FetcherArguments = @("--help")
}

& $VenvPython $FetcherScript @FetcherArguments
exit $LASTEXITCODE
