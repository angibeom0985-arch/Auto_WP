param(
    [Parameter(Mandatory = $true)]
    [string]$Message,
    [string]$Remote = "auto_wp",
    [string]$Branch = "main",
    [switch]$Push
)

$ErrorActionPreference = "Stop"

Write-Host "[safe-commit] staging safe files..."

# Commit only code/configuration files under source tree.
# Do not include runtime outputs or sensitive local settings.
git add -- "Auto_WP_V8.13.py" ".gitignore" "scripts/safe_commit.ps1"

# Extra safety: explicitly unstage sensitive files if they were staged elsewhere.
git reset -- "setting/license.json" "setting/setting.json" 2>$null | Out-Null

$sensitive = @(
    "setting/license.json",
    "setting/setting.json",
    "setting/debug.log"
)
$staged = git diff --cached --name-only
foreach ($item in $sensitive) {
    if ($staged -contains $item) {
        Write-Error "[safe-commit] sensitive file staged: $item"
        exit 1
    }
}

if (-not (git diff --cached --name-only)) {
    Write-Host "[safe-commit] nothing staged."
    exit 0
}

git commit -m "$Message"
Write-Host "[safe-commit] commit created."

if ($Push) {
    git push $Remote $Branch
    Write-Host "[safe-commit] pushed to $Remote/$Branch."
}
