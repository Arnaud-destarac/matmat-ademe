<#
Enchaine l'etape gmrio_to_snac_s pour chaque annee de base (2015, 2019) et
chaque version d'Exiobase (3.9.6, 3.10.2), en adaptant les chemins (annee,
version) dans le fichier de settings JSON avant chaque run.

A executer depuis l'environnement matmat-ademe (pipeline porte dans
src/matmat/workflows/pipelines/accounts/gmrio_to_snac_s).
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$gmrioSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\2-gmrio_to_snac_s\gmrio_to_snac_S_FR.json"

$baseYears = 2015, 2019
$versions  = "3.9.6", "3.10.2"

Set-Location $projectDir

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Remplace toutes les occurrences "_20xx" (annee) par "_$Year", pour que
    # le dossier version_annee et le sous-dossier version_pxp_annee restent
    # coherents entre eux.
    return [regex]::Replace($Path, "_20\d{2}", "_$Year")
}

function Set-VersionInPath {
    param(
        [string]$Path,
        [string]$Version
    )
    # Remplace toute occurrence d'un numero de version Exiobase (ex. 3.10.2,
    # 3.9.6) par la version demandee, en conservant le reste du chemin
    # (annee, sous-dossiers) inchange.
    return [regex]::Replace($Path, "\d+\.\d+\.\d+", $Version)
}

function Set-GmrioToSnacSSettings {
    param(
        [int]$Year,
        [string]$Version
    )

    $settings = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json

    $settings.path_in.accounts = Set-YearInPath -Path $settings.path_in.accounts -Year $Year
    $settings.path_in.accounts = Set-VersionInPath -Path $settings.path_in.accounts -Version $Version
    $settings.path_out          = Set-YearInPath -Path $settings.path_out -Year $Year
    $settings.path_out          = Set-VersionInPath -Path $settings.path_out -Version $Version

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($gmrioSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($year in $baseYears) {
    foreach ($version in $versions) {
        Write-Host "=== base_year=$year / version=$version : gmrio_to_snac_s ===" -ForegroundColor Cyan

        Set-GmrioToSnacSSettings -Year $year -Version $version

        uv run python -m matmat.cli -p gmrio_to_snac_s -st $gmrioSettingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Echec gmrio_to_snac_s pour base_year=$year / version=$version (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }
}
