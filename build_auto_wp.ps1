param(
    [string]$Entry = "Auto_WP_V8.13.py",
    [string]$Name = "Auto_WP_V8.13"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$icon = "setting\etc\auto_wp.ico"
if (-not (Test-Path $icon)) {
    throw "아이콘 파일을 찾을 수 없습니다: $icon"
}

$entryPath = $Entry
if (-not (Test-Path $entryPath)) {
    throw "엔트리 파일을 찾을 수 없습니다: $entryPath"
}

$env:PYTHONUTF8 = "1"

# 빌드 포함용 setting 폴더를 임시로 정리 (민감/런타임 파일 제외)
$settingSource = Join-Path $root "setting"
$settingTemp = Join-Path $root ".build_setting"
if (Test-Path $settingTemp) {
    Remove-Item -Recurse -Force $settingTemp
}
Copy-Item -Recurse -Force $settingSource $settingTemp

# 금지 아티팩트를 재귀적으로 제거
$forbiddenFileRegex = '^(license\.json|profile_registry\.json|debug.*\.log)$'
Get-ChildItem -Path $settingTemp -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match $forbiddenFileRegex } |
    ForEach-Object { Remove-Item -Force $_.FullName -ErrorAction SilentlyContinue }

Get-ChildItem -Path $settingTemp -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "chrome_profile" } |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --exclude-module PyQt5 `
    --name $Name `
    --icon $icon `
    --add-data ".build_setting;setting" `
    $entryPath

if (Test-Path $settingTemp) {
    Remove-Item -Recurse -Force $settingTemp
}

Write-Host "빌드 완료: dist\$Name.exe"
