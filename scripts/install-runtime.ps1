#requires -Version 7.4
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$installRoot = Split-Path -Parent $PSScriptRoot
$env:UV_PYTHON_INSTALL_DIR = Join-Path $installRoot 'runtime/python'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $installRoot 'runtime/venv'
$env:UV_CACHE_DIR = Join-Path $installRoot 'runtime/cache'
$env:UV_LINK_MODE = 'copy'
$env:UV_HTTP_RETRIES = '0'

& (Join-Path $installRoot 'tools/uv.exe') sync --directory (Join-Path $installRoot 'app') --locked --no-default-groups --python 3.12.10 --managed-python --no-editable
& (Join-Path $installRoot 'runtime/venv/Scripts/python.exe') -I -m playwright install chromium --no-shell
