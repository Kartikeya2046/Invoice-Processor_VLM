# Run all database migrations in order
# Usage: .\scripts\migrate.ps1

$migrations = @(
    "database/migrations/001_initial_schema.sql",
    "database/migrations/002_phase6_pipeline.sql"
)

foreach ($file in $migrations) {
    Write-Host "Applying $file..."
    Get-Content $file | docker exec -i docextract_postgres psql -U postgres -d docextract
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to apply $file" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK: $file applied successfully" -ForegroundColor Green
}

Write-Host "All migrations applied successfully." -ForegroundColor Green
