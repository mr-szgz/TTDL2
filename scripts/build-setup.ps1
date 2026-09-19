#requires -Version 7.4
param(
    [string]$IsccPath = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"$').Matches.Groups[1].Value
New-Item -ItemType Directory -Force build/bootstrap | Out-Null
Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/0.11.11/uv-x86_64-pc-windows-msvc.zip' -OutFile build/bootstrap/uv.zip
Expand-Archive -LiteralPath build/bootstrap/uv.zip -DestinationPath build/bootstrap/uv -Force
Invoke-WebRequest 'https://raw.githubusercontent.com/astral-sh/uv/0.11.11/LICENSE-MIT' -OutFile build/bootstrap/LICENSE-MIT
Invoke-WebRequest 'https://raw.githubusercontent.com/astral-sh/uv/0.11.11/LICENSE-APACHE' -OutFile build/bootstrap/LICENSE-APACHE
& $IsccPath "/DAppVersion=$version" scripts/installer.iss
$installer = Join-Path $projectRoot "dist\$version\TTDL2-$version-windows-x64-Setup.exe"
Get-FileHash -Algorithm SHA256 -LiteralPath $installer |
    ForEach-Object { '{0}  {1}' -f $_.Hash.ToLowerInvariant(), (Split-Path -Leaf $_.Path) } |
    Set-Content -LiteralPath "$installer.sha256" -Encoding ascii
Get-Item -LiteralPath $installer
