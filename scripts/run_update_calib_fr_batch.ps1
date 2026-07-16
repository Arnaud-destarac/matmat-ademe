<#
Enchaine l'etape update_calib_fr pour chaque annee de base, en adaptant les
chemins (annee) dans le fichier de settings JSON avant chaque run.

Suppose que l'etape gmrio_to_snac_s a deja ete executee au prealable (cf.
run_calib_fr_batch.ps1) et que ses sorties sont disponibles pour chaque
annee.

NB : le pipeline "update_calib_fr" n'est pour l'instant pas porte dans
matmat-ademe (src/matmat/workflows/pipelines/accounts/ ne contient que
"aggregation" et "gmrio_to_snac_s" ; -p update_calib_fr n'existe pas dans
cli.py). Il n'existe que dans l'ancien wheel installe pour le projet
datapack (matmat==0.9.0b0). En attendant qu'il soit porte ici, l'etape
update_calib_fr est affichee en TODO (commande a lancer manuellement
depuis l'environnement datapack, ou a activer ici une fois le pipeline
disponible dans matmat-ademe).
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$calibSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\3-update_calib_fr\update_calib_fr_PlaneFR.json"

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

function Set-UpdateCalibFrSettings {
    param(
        [int]$Year
    )

    $settings = Get-Content -Raw -Path $calibSettingsPath | ConvertFrom-Json

    $settings.path_in.newer_accounts = Set-YearInPath -Path $settings.path_in.newer_accounts -Year $Year
    $settings.path_in.older_accounts = Set-YearInPath -Path $settings.path_in.older_accounts -Year $Year
    $settings.path_out                = Set-YearInPath -Path $settings.path_out -Year $Year

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($calibSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($year in $baseYears) {
    Write-Host "=== base_year=$year : update_calib_fr ===" -ForegroundColor Cyan

    Set-UpdateCalibFrSettings -Year $year

    # TODO : decommenter une fois le pipeline "update_calib_fr" porte dans
    # matmat-ademe (choix -p update_calib_fr absent de cli.py pour le
    # moment). En attendant, la commande equivalente existe dans
    # l'environnement du projet datapack :
    #   uv run python -m matmat.cli -p update_calib_fr -st $calibSettingsPath
    Write-Host "update_calib_fr non disponible dans matmat-ademe : settings mis a jour ($calibSettingsPath), run a faire manuellement (cf. commentaire dans le script)." -ForegroundColor Yellow
}
