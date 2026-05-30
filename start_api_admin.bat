@echo off
cd /d "%~dp0"

where pixi >nul 2>nul
if errorlevel 1 (
  echo Pixi was not found in PATH.
  exit /b 1
)

if not exist ".pixi" (
  pixi install
  if errorlevel 1 exit /b 1
)

pixi run serve
