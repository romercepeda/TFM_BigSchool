# Starts the local-production stack. Invoked by the "PortfolioIA - Start" scheduled
# task at 13:00 Europe/Madrid (see scripts/README-docker-window.md), but safe to
# run by hand any time.

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

$dockerReady = $false
try { docker info *> $null; $dockerReady = $LASTEXITCODE -eq 0 } catch {}

if (-not $dockerReady) {
    Write-Output "Docker Desktop not running — launching it."
    Start-Process $DockerDesktop

    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        try { docker info *> $null; if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break } } catch {}
        Start-Sleep -Seconds 3
    }
}

if (-not $dockerReady) {
    Write-Error "Docker did not become ready within 3 minutes — aborting."
    exit 1
}

Set-Location $RepoRoot
docker compose up -d
Write-Output "Portfolio IA started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')."
