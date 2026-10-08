# Pull, commit everything, and push this repo.
# Windows push script. Uses the current remote and the main branch.
#
#   .\win-push.ps1
#   .\win-push.ps1 "commit message"

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Message
)

Set-Location -Path $PSScriptRoot

Write-Host "Checking for newer files online first"
git pull --no-rebase
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git add --all .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git diff --cached --quiet
$nothingToCommit = $LASTEXITCODE -eq 0

if ($nothingToCommit) {
    Write-Host "Nothing to commit."
    git push -u origin main
    exit $LASTEXITCODE
}

$comment = ""
if ($Message) { $comment = ($Message -join " ").Trim() }

if (-not $comment) {
    Write-Host "####################################"
    Write-Host "Write your commit comment!"
    Write-Host "####################################"
    $comment = Read-Host
}

if (-not $comment) {
    Write-Host "Commit comment is empty. Stopped."
    exit 1
}

git commit -m $comment
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git push -u origin main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "################################################################"
Write-Host "###################    Git Push Done      ######################"
Write-Host "################################################################"
