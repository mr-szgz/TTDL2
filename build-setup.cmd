@echo off
pwsh -NoProfile -File "%~dp0scripts\build-setup.ps1" %*
exit /b %errorlevel%
