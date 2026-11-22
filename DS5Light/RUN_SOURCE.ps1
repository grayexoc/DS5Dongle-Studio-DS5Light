param([switch]$StrongAiTest = $true)
$ErrorActionPreference = 'Stop'

$python = $env:DS5LIGHT_RUN_PYTHON
if (!$python) {
    $localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    $documents = [Environment]::GetFolderPath('MyDocuments')
    $sharedPython = Join-Path $documents 'Codex/DS5Light/.venv/Scripts/python.exe'
    $python = @($localPython, $sharedPython) |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if (!$python) {
        $python = (Get-Command python -CommandType Application).Source
    }
}

Push-Location -LiteralPath $PSScriptRoot
$previousAiTest = $env:DS5LIGHT_STRONG_AI_TEST
try {
    $env:DS5LIGHT_STRONG_AI_TEST = if ($StrongAiTest) { '1' } else { '0' }
    & $python -B (Join-Path $PSScriptRoot 'app.py') @args
    $appExit = $LASTEXITCODE
} finally {
    $env:DS5LIGHT_STRONG_AI_TEST = $previousAiTest
    Pop-Location
}
exit $appExit
