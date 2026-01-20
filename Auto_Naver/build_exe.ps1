$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$spec = Join-Path $root "Auto_Naver_Blog_V5.1.spec"
$dist = Join-Path $root "dist"
$work = Join-Path $root "build"

pyinstaller $spec --distpath $dist --workpath $work
