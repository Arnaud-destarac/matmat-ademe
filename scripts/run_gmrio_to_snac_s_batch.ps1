<#
Enchaine l'etape gmrio_to_snac_s pour chaque annee de base (2015, 2019), en
adaptant les chemins (annee) dans le fichier de settings JSON avant chaque
run.

A executer depuis l'environnement matmat-ademe (pipeline porte dans
src/matmat/workflows/pipelines/accounts/gmrio_to_snac_s).
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$gmrioSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\2-gmrio_to_snac_s\gmrio_to_snac_S_FR.json"

$baseYears = 2015, 2019

Set-Location $projectDir

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Remplace la derniere occurrence "_20xx" (annee) par "_$Year", en
    # conservant le reste du chemin (version, sous-dossiers) inchange.
    return [regex]::Replace($Path, "_20\d{2}(?!.*_20\d{2})", "_$Year")
}

function Set-GmrioToSnacSSettings {
    param(
        [int]$Year
    )

    $settings = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json

    $settings.path_in.accounts = Set-YearInPath -Path $settings.path_in.accounts -Year $Year
    $settings.path_out          = Set-YearInPath -Path $settings.path_out -Year $Year

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($gmrioSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($year in $baseYears) {
    Write-Host "=== base_year=$year : gmrio_to_snac_s ===" -ForegroundColor Cyan

    Set-GmrioToSnacSSettings -Year $year

    uv run python -m matmat.cli -p gmrio_to_snac_s -st $gmrioSettingsPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec gmrio_to_snac_s pour base_year=$year (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
