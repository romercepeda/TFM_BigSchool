# Stops the local-production stack (containers only — Docker Desktop itself is
# left running). Invoked by the "PortfolioIA - Stop" scheduled task at 19:00
# Europe/Madrid (see scripts/README-docker-window.md), but safe to run by hand.

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
docker compose stop
Write-Output "Portfolio IA stopped at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')."
