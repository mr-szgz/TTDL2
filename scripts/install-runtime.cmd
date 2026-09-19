@echo off
setlocal
set "UV_PYTHON_INSTALL_DIR=%~dp0runtime\python"
set "UV_PROJECT_ENVIRONMENT=%~dp0runtime\venv"
set "UV_CACHE_DIR=%~dp0runtime\cache"
set "UV_LINK_MODE=copy"
set "UV_HTTP_RETRIES=0"
echo Installing Python 3.12.10 and application dependencies...
"%~dp0tools\uv.exe" sync --directory "%~dp0app" --locked --no-default-groups --python 3.12.10 --managed-python --no-editable && "%~dp0runtime\venv\Scripts\python.exe" -I -m playwright install chromium --no-shell
exit /b %errorlevel%
