#requires -Version 7.4
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
uv sync --locked --extra test
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $python -m playwright install chromium
& $python -m pytest -q
$version = & $python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
$releaseDirectory = Join-Path $projectRoot "dist\$version"
uv build --no-sources --out-dir $releaseDirectory

# Verify the wheel from outside the checkout, using its installed package and worker.
$verifyDirectory = Join-Path $releaseDirectory ('verify-' + [guid]::NewGuid().ToString('N'))
uv venv $verifyDirectory --python $python
$verifyPython = Join-Path $verifyDirectory 'Scripts\python.exe'
$constraints = Join-Path $releaseDirectory 'constraints.txt'
uv export --locked --extra test --no-emit-project --format requirements-txt --output-file $constraints | Out-Null
$wheel = Join-Path $releaseDirectory "ttdl2-$version-py3-none-any.whl"
uv pip install --python $verifyPython --constraint $constraints "${wheel}[test]"
Set-Location -LiteralPath $verifyDirectory
& $verifyPython -c 'import pathlib, sys, tiktok_downloader; assert pathlib.Path(tiktok_downloader.__file__).is_relative_to(sys.prefix); print(tiktok_downloader.__file__)'
& $verifyPython -m pytest (Join-Path $projectRoot 'tests') --import-mode=importlib -q
Set-Location -LiteralPath $projectRoot

$sourceArchive = Join-Path $releaseDirectory "ttdl2-$version.tar.gz"
Get-FileHash -Algorithm SHA256 -LiteralPath $wheel, $sourceArchive |
    ForEach-Object { '{0}  {1}' -f $_.Hash.ToLowerInvariant(), (Split-Path -Leaf $_.Path) } |
    Set-Content -LiteralPath (Join-Path $releaseDirectory 'SHA256SUMS.txt') -Encoding ascii
Write-Output "Release artifacts verified: $releaseDirectory"
