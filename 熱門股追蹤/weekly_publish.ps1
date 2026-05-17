$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Deploy = Join-Path $Root "hot-stocks-deploy"
$ReportDir = Join-Path $Root "reports"
$LogFile = Join-Path $Root "weekly_publish.log"

function Write-Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogFile -Encoding UTF8 -Value "[$stamp] $Message"
}

try {
    Write-Log "Start weekly publish."
    $RunStarted = Get-Date
    New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

    $ReportBat = Get-ChildItem -LiteralPath $Root -Filter "*.bat" -File |
        Where-Object {
            (Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8) -match "hot_stocks_weekly\.py"
        } |
        Select-Object -First 1

    if (-not $ReportBat) {
        throw "Report batch file not found."
    }
    if (-not (Test-Path -LiteralPath $Deploy)) {
        throw "Deploy folder not found: $Deploy"
    }

    Push-Location $Root
    try {
        & $ReportBat.FullName --no-pause
        if ($LASTEXITCODE -ne 0) {
            throw "Report batch failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $report = Get-ChildItem -LiteralPath $ReportDir -Filter "*.html" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $report) {
        throw "No generated weekly report file found."
    }
    if ($report.LastWriteTime -lt $RunStarted.AddMinutes(-2)) {
        throw "Latest report is stale: $($report.FullName)"
    }

    $target = Join-Path $Deploy "index.html"
    Copy-Item -LiteralPath $report.FullName -Destination $target -Force
    Write-Log "Copied $($report.Name) to hot-stocks-deploy\index.html."

    & git -C $Deploy add index.html
    if ($LASTEXITCODE -ne 0) {
        throw "git add failed with exit code $LASTEXITCODE"
    }

    $status = & git -C $Deploy status --porcelain
    if ([string]::IsNullOrWhiteSpace(($status | Out-String))) {
        Write-Log "No deploy changes to commit."
    }
    else {
        $commitDate = Get-Date -Format "yyyy-MM-dd"
        & git -C $Deploy commit -m "weekly update $commitDate"
        if ($LASTEXITCODE -ne 0) {
            throw "git commit failed with exit code $LASTEXITCODE"
        }
    }

    & git -C $Deploy push origin main
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed with exit code $LASTEXITCODE"
    }

    Write-Log "Finished weekly publish."
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    throw
}
