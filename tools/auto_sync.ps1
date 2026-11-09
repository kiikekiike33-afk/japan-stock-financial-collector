# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    japan-stock-financial-collector GitHub 自動同期スクリプト (auto-sync専用)
#>

param(
    [string]$BranchName = "auto-sync",
    [string]$RemoteName = "origin"
)

if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Git\cmd;" + [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogDir "auto_sync.log"
$MuseShareDir = "C:\MuseShare\japan-stock-financial-collector"
$MuseLogFile = Join-Path $MuseShareDir "auto_sync.log"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-SyncLog {
    param([string]$Message, [string]$Level = "INFO")
    $Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $Line = "[$Timestamp] [$Level] $Message"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    if (Test-Path $MuseShareDir) {
        try { Add-Content -Path $MuseLogFile -Value $Line -Encoding UTF8 -ErrorAction SilentlyContinue } catch {}
    }
    Write-Output $Line
}

Push-Location $RepoRoot
try {
    Write-SyncLog "=== auto_sync start (RepoRoot: $RepoRoot, Branch: $BranchName) ==="

    if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
        Write-SyncLog "Git repo not found." "ERROR"
        exit 1
    }

    $Remotes = (git remote) -split "`r?`n"
    if (-not ($Remotes -contains $RemoteName)) {
        Write-SyncLog "Remote $RemoteName not found." "ERROR"
        exit 2
    }

    if ($BranchName -eq "main" -or $BranchName -eq "master") {
        Write-SyncLog "Safety violation: main/master push prohibited." "ERROR"
        exit 3
    }

    $CurrentBranch = (git rev-parse --abbrev-ref HEAD).Trim()
    if ($CurrentBranch -ne $BranchName) {
        $LocalBranches = (git branch --list $BranchName)
        if ($LocalBranches) {
            git checkout $BranchName 2>&1 | Out-Null
        } else {
            git checkout -b $BranchName "origin/$BranchName" 2>&1 | Out-Null
        }
        Write-SyncLog "Switched branch to $BranchName"
    }

    $RemoteBranchExists = git ls-remote --heads $RemoteName $BranchName
    if ($RemoteBranchExists) {
        Write-SyncLog "Pulling with rebase from $RemoteName $BranchName..."
        $HasLocalChanges = (git status --porcelain)
        if ($HasLocalChanges) {
            git stash push -u -m "auto-sync-temp" 2>&1 | Out-Null
        }
        $PullOutput = git pull --rebase $RemoteName $BranchName 2>&1
        $PullStatus = $LASTEXITCODE
        if ($HasLocalChanges) {
            git stash pop 2>&1 | Out-Null
        }
        if ($PullStatus -ne 0) {
            Write-SyncLog "Pull failed or conflict occurred. Aborting rebase." "ERROR"
            git rebase --abort 2>&1 | Out-Null
            exit 4
        }
    }

    $StatusOutput = git status --porcelain
    if (-not $StatusOutput) {
        Write-SyncLog "No changes to commit. Nothing to do."
        exit 0
    }

    Write-SyncLog "Changes detected. Staging..."
    git add . 2>&1 | Out-Null

    $CommitMsg = "auto-sync: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    git commit -m $CommitMsg 2>&1 | Out-Null

    Write-SyncLog "Pushing to origin/$BranchName..."
    $PushOutput = git push $RemoteName $BranchName 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-SyncLog "Push failed: $PushOutput" "ERROR"
        exit 5
    }

    Write-SyncLog "=== auto_sync completed successfully ==="
}
catch {
    Write-SyncLog "Unexpected error: $($_.Exception.Message)" "ERROR"
    exit 99
}
finally {
    Pop-Location
}
