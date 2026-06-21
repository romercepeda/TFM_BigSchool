<#
.SYNOPSIS
    Database management script for BigSchool.

.DESCRIPTION
    Single entry point for all database operations.
    All commands run inside the backend Docker container so no local
    Python environment is needed.

    IMPORTANT — WHEN TO UPDATE THIS SCRIPT:
    ----------------------------------------
    Any time you add, modify, or remove a SQLAlchemy model in backend/app/db/models/,
    you must:
      1. Run:  .\scripts\db.ps1 generate "describe-what-changed"
      2. Review the generated file in backend/migrations/versions/
      3. Run:  .\scripts\db.ps1 upgrade
      4. Commit both the model file AND the migration file together.

.PARAMETER Command
    upgrade        Apply all pending migrations to the database.
    downgrade      Roll back the last migration.
    generate       Generate a new migration from model changes. Requires -Message.
    history        Show all migrations (applied and pending).
    current        Show which migration is currently applied.
    reset          Drop all tables and re-apply all migrations from scratch.
                   WARNING: destroys all data. Only use in development.
    seed           Insert base seed data (indicator catalog, etc.).
                   Safe to run multiple times (idempotent).

.PARAMETER Message
    Short description for the migration file (used with 'generate').
    Example: "add holding table"

.EXAMPLE
    .\scripts\db.ps1 upgrade
    .\scripts\db.ps1 generate "add holding and lot tables"
    .\scripts\db.ps1 history
    .\scripts\db.ps1 reset
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("upgrade", "downgrade", "generate", "history", "current", "reset", "seed")]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Message = ""
)

Set-Location (Split-Path $PSScriptRoot -Parent)

# Verify the backend container is running before doing anything.
$running = docker compose ps --services --filter "status=running" 2>$null
if ($running -notcontains "backend") {
    Write-Error "The backend container is not running. Start it with: docker compose up -d"
    exit 1
}

switch ($Command) {

    "upgrade" {
        Write-Host "Applying all pending migrations..." -ForegroundColor Cyan
        docker compose exec backend alembic upgrade head
    }

    "downgrade" {
        Write-Host "Rolling back the last migration..." -ForegroundColor Yellow
        docker compose exec backend alembic downgrade -1
    }

    "generate" {
        if (-not $Message) {
            Write-Error "A message is required. Example: .\scripts\db.ps1 generate `"add holding table`""
            exit 1
        }
        Write-Host "Generating migration: $Message" -ForegroundColor Cyan
        docker compose exec backend alembic revision --autogenerate -m $Message
        Write-Host ""
        Write-Host "Review the generated file in backend/migrations/versions/ before applying." -ForegroundColor Yellow
        Write-Host "Then run: .\scripts\db.ps1 upgrade" -ForegroundColor Yellow
    }

    "history" {
        Write-Host "Migration history:" -ForegroundColor Cyan
        docker compose exec backend alembic history --verbose
    }

    "current" {
        Write-Host "Current database revision:" -ForegroundColor Cyan
        docker compose exec backend alembic current
    }

    "reset" {
        Write-Host ""
        Write-Host "WARNING: This will drop all tables and re-apply all migrations." -ForegroundColor Red
        Write-Host "All data in the database will be permanently lost." -ForegroundColor Red
        Write-Host ""
        $confirm = Read-Host "Type 'yes' to continue"
        if ($confirm -ne "yes") {
            Write-Host "Cancelled." -ForegroundColor Yellow
            exit 0
        }
        Write-Host "Dropping all tables..." -ForegroundColor Yellow
        docker compose exec backend alembic downgrade base
        Write-Host "Re-applying all migrations..." -ForegroundColor Cyan
        docker compose exec backend alembic upgrade head
        Write-Host "Database reset complete." -ForegroundColor Green
    }

    "seed" {
        Write-Host "Running seed data..." -ForegroundColor Cyan
        # Seed commands will be added here as we implement the indicator catalog (Spec D05)
        # and any other seed data. For now this is a placeholder.
        Write-Host "No seed data defined yet. Will be added with the indicator catalog (Spec D05)." -ForegroundColor Yellow
    }
}
