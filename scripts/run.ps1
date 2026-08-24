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
$CorpusScript = Join-Path $PSScriptRoot "corpus_tool.py"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "The private Python environment is missing. Run .\scripts\bootstrap.ps1 first."
}

if ($FetcherArguments.Count -eq 0) {
    $FetcherArguments = @("--help")
}

$SelectedScript = $FetcherScript
$ToolArguments = $FetcherArguments
if ($FetcherArguments[0] -eq "corpus") {
    $SelectedScript = $CorpusScript
    if ($FetcherArguments.Count -gt 1) {
        $ToolArguments = $FetcherArguments[1..($FetcherArguments.Count - 1)]
    }
    else {
        $ToolArguments = @("--help")
    }
}

if (-not (Test-Path -LiteralPath $SelectedScript -PathType Leaf)) {
    throw "The requested Skill entrypoint is missing: $([System.IO.Path]::GetFileName($SelectedScript))"
}

& $VenvPython $SelectedScript @ToolArguments
exit $LASTEXITCODE
