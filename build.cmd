@echo off
pwsh -NoProfile -File "%~dp0scripts\build.ps1"
exit /b %errorlevel%
