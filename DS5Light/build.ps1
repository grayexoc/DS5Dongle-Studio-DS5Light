$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force reports | Out-Null
New-Item -ItemType Directory -Force .build-temp | Out-Null
$env:TEMP = (Resolve-Path '.build-temp').Path
$env:TMP = $env:TEMP
$ds5BuildPython = $env:DS5LIGHT_BUILD_PYTHON
if ($ds5BuildPython) {
    if (!(Test-Path -LiteralPath $ds5BuildPython -PathType Leaf)) { throw 'Invalid build Python path' }
} else {
    $ds5BuildPython = '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $ds5BuildPython)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python venv setup failed' }
    }
    & $ds5BuildPython -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
$ds5AppVersion = & $ds5BuildPython -B -c "from app_version import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or $ds5AppVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid app version' }
$ds5PackageDirectory = Split-Path -Parent $PSScriptRoot
$ds5BuildSuffix = if ($env:DS5LIGHT_EXPERIMENTAL -eq '1') { '-Experimental' } else { '' }
$ds5PackagePath = Join-Path $ds5PackageDirectory "DS5Light-win-x64-v$ds5AppVersion$ds5BuildSuffix.zip"
if (Test-Path -LiteralPath $ds5PackagePath) { throw "Package already exists; update app_version.py before building: $ds5PackagePath" }
if ($env:DS5LIGHT_RUN_TESTS -eq '1') {
    & $ds5BuildPython -m unittest discover -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw '테스트 실패' }
}
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /platform:x64 /target:exe /out:ProcessCapture.exe '.\native\ProcessCapture.cs'
if ($LASTEXITCODE -ne 0) { throw 'Process capture helper build failed' }
& (Join-Path $PSScriptRoot 'prepare_assets.ps1')
# Explicit runtime assets avoid shipping unused images, source artwork and
# duplicate SVG provenance/notices (preserved by package_notices.py).
$ds5DataFiles = @(
    'assets/dslight.ico;assets',
    'assets/diagnostic-bg-120.png;assets',
    'assets/diagnostic-bg-160.png;assets',
    'assets/diagnostic-bg-240.png;assets',
    'assets/diagnostic-bg-320.png;assets',
    'assets/ds5-light-logo.svg;assets',
    'assets/dualsense-controls.svg;assets',
    'assets/diagnostic-controller.svg;assets',
    'assets/edge;assets/edge',
    'vendor/ds5audio_original.py;vendor',
    'vendor/LICENSE-Studio.txt;vendor',
    'vendor/tksvg0.16/pkgIndex.tcl;vendor/tksvg0.16',
    'vendor/tksvg0.16/tksvg016t.dll;vendor/tksvg0.16'
)
$ds5BundleArguments = @('--noconfirm','--clean','--onedir','--windowed','--name','DS5Light','--distpath','dist','--icon','assets/dslight.ico','--manifest','DS5Light.manifest','--add-binary','ProcessCapture.exe;.','--exclude-module','matplotlib','--exclude-module','pandas','--exclude-module','torch','--exclude-module','IPython')
foreach ($ds5DataFile in $ds5DataFiles) { $ds5BundleArguments += @('--add-data',$ds5DataFile) }
$ds5BundleArguments += 'app.py'
& $ds5BuildPython -m PyInstaller @ds5BundleArguments
if ($LASTEXITCODE -ne 0) { throw '빌드 실패' }
# Windows 10/11 uses the operating system UCRT; omit locally collected OS DLLs.
$ds5Internal = (Resolve-Path 'dist/DS5Light/_internal').Path
Get-ChildItem -LiteralPath $ds5Internal -File | Where-Object { $_.Name -eq 'ucrtbase.dll' -or $_.Name -like 'api-ms-win-*.dll' } | ForEach-Object {
    if ($_.DirectoryName -ne $ds5Internal) { throw 'Unexpected DLL location' }
    Remove-Item -LiteralPath $_.FullName
}
& $ds5BuildPython package_notices.py
if ($LASTEXITCODE -ne 0) { throw '라이선스 고지 준비 실패' }
# Copy release documents and the three user-provided Studio profiles.
Copy-Item MAPPING_GUIDE_KO.md,DPI_LAYOUT_KO.md,LICENSE.txt,LICENSE_EN.txt,README.txt,DISTRIBUTION_POLICY_KO.md,default_config.json,README_KO.txt,SOURCES.md,README.md,PRODUCT_KO.md,SETUP.md,SETUP_KO.md,RELEASE_NOTES.md -Destination dist/DS5Light
$ds5PresetOutput = Join-Path $PSScriptRoot 'dist/DS5Light/Studio Presert'
New-Item -ItemType Directory -Force -Path $ds5PresetOutput | Out-Null
foreach ($ds5PresetName in @('DS_Native.json','Audio_Haptic_01.json','Audio_Haptic_02.json')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Studio Presert/$ds5PresetName") -Destination $ds5PresetOutput
}
Copy-Item -LiteralPath 'Studio Presert/README.txt','Studio Presert/README_KO.txt' -Destination $ds5PresetOutput
$ds5RetiredRecommendations = Join-Path $PSScriptRoot 'dist/DS5Light/recommend-slots.json'
if (Test-Path -LiteralPath $ds5RetiredRecommendations) { Remove-Item -LiteralPath $ds5RetiredRecommendations }
$ds5RetiredSlots = Join-Path $PSScriptRoot 'dist/DS5Light/ds5dongle-slots.json'
if (Test-Path -LiteralPath $ds5RetiredSlots) { Remove-Item -LiteralPath $ds5RetiredSlots }
# No preset preferences are shipped. Preferences are created by the running app.
$ds5OldPreferences = Join-Path $PSScriptRoot 'dist/DS5Light/preferences.json'
if (Test-Path -LiteralPath $ds5OldPreferences) { Remove-Item -LiteralPath $ds5OldPreferences }
# Never ship the retired experimental guide, including from a reused dist tree.
$ds5RetiredGuide = Join-Path $PSScriptRoot 'dist/DS5Light/EXPERIMENTAL_KO.md'
if (Test-Path -LiteralPath $ds5RetiredGuide) { Remove-Item -LiteralPath $ds5RetiredGuide }
Compress-Archive -Path 'dist/DS5Light' -DestinationPath $ds5PackagePath
Write-Output "Package: $ds5PackagePath"
