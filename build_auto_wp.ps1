param(
    [string]$Entry = "Auto_WP_V8.13.py",
    [string]$Name = "Auto_WP_V8.13"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$icon = Join-Path $root "setting\etc\auto_wp.ico"
if (-not (Test-Path $icon)) {
    throw "아이콘 파일을 찾을 수 없습니다: $icon"
}

$entryPath = Join-Path $root $Entry
if (-not (Test-Path $entryPath)) {
    throw "엔트리 파일을 찾을 수 없습니다: $entryPath"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $Name `
    --icon $icon `
    --add-data "setting;setting" `
    $entryPath

Write-Host "빌드 완료: dist\$Name\$Name.exe"
