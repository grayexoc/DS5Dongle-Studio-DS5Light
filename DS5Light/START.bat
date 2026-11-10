@echo off
cd /d "%~dp0"
if exist "dist\DS5Light\DS5Light.exe" (
    start "" "dist\DS5Light\DS5Light.exe"
) else (
    echo Build output missing. See README_KO.txt.
    pause
)
