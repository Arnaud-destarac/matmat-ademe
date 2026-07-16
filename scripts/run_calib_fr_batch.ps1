<#
Enchaine, pour chaque annee de base, l'etape gmrio_to_snac_s puis l'etape
update_calib_fr, en adaptant les chemins (annee) dans les fichiers de
settings JSON avant chaque run.

NB : le pipeline "update_calib_fr" n'est pour l'instant pas porte dans
matmat-ademe (src/matmat/workflows/pipelines/accounts/ ne contient que
"aggregation" et "gmrio_to_snac_s" ; -p update_calib_fr n'existe pas dans
cli.py). Il n'existe que dans l'ancien wheel installe pour le projet
datapack (matmat==0.9.0b0). En attendant qu'il soit porte ici, seule
l'etape gmrio_to_snac_s est executee automatiquement ; l'etape
update_calib_fr est affichee en TODO (commande a lancer manuellement
depuis l'environnement datapack, ou a activer ici une fois le pipeline
disponible dans matmat-ademe).
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$gmrioSettingsPath  = Join-Path $projectDir "data\4-PlaneFR\Settings\2-gmrio_to_snac_s\gmrio_to_snac_S_FR.json"
$calibSettingsPath  = Join-Path $projectDir "data\4-PlaneFR\Settings\3-update_calib_fr\update_calib_fr_PlaneFR.json"
$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_France_shocks.json"
$shocksDir          = Join-Path $projectDir "data\3-workshops\2-shocks\1-transitions_2050"

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

function Set-UpdateCalibFrSettings {
    param(
        [int]$Year
    )

    $settings = Get-Content -Raw -Path $calibSettingsPath | ConvertFrom-Json

    $settings.path_in.newer_accounts = Set-YearInPath -Path $settings.path_in.newer_accounts -Year $Year
    $settings.path_in.older_accounts = Set-YearInPath -Path $settings.path_in.older_accounts -Year $Year
    $settings.path_out                = Set-YearInPath -Path $settings.path_out -Year $Year

    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($calibSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# Dossier de sortie de base (ex. "...\Module_PlaneFR\data\3.10.2"), capture
# une seule fois depuis le path_out initial pour ne pas deriver d'une valeur
# deja ecrasee par une iteration precedente.
$initialEngineSettings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
$engineOutBaseDir = Split-Path -Parent $initialEngineSettings.path_out

function Set-EngineSettings {
    param(
        # $null pour le run baseline (pas de choc), sinon nom du sous-dossier
        # de scenario (ex. "S1_2050"). Pas de type [string] ici : PowerShell
        # convertirait silencieusement un $null passe en argument en "",
        # ce qui casserait le test $null -eq $ScenarioName ci-dessous.
        $ScenarioName
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    # path_in.accounts reste inchange (fixe a base-year_2015)

    $outBaseDir = $engineOutBaseDir

    if ($null -eq $ScenarioName) {
        $settings.path_in.shock = $null
        $settings.path_out       = Join-Path $outBaseDir "base-year_2015"
    }
    else {
        $settings.path_in.shock = ".\3-workshops\2-shocks\1-transitions_2050\$ScenarioName"
        $settings.path_out       = Join-Path $outBaseDir $ScenarioName
    }

    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($year in $baseYears) {
    Write-Host "=== base_year=$year : gmrio_to_snac_s ===" -ForegroundColor Cyan

    Set-GmrioToSnacSSettings -Year $year

    # uv run python -m matmat.cli -p gmrio_to_snac_s -st $gmrioSettingsPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec gmrio_to_snac_s pour base_year=$year (code $LASTEXITCODE)" -ForegroundColor Red
        continue
    }

    Write-Host "=== base_year=$year : update_calib_fr ===" -ForegroundColor Cyan

    Set-UpdateCalibFrSettings -Year $year

    # TODO : decommenter une fois le pipeline "update_calib_fr" porte dans
    # matmat-ademe (choix -p update_calib_fr absent de cli.py pour le
    # moment). En attendant, la commande equivalente existe dans
    # l'environnement du projet datapack :
    uv run python -m matmat.cli -p update_calib_fr -st $calibSettingsPath
    Write-Host "update_calib_fr non disponible dans matmat-ademe : settings mis a jour ($calibSettingsPath), run a faire manuellement (cf. commentaire dans le script)." -ForegroundColor Yellow
}

# === Etape engine : baseline (sans choc) puis un run par scenario present
# dans data\3-workshops\2-shocks\1-transitions_2050 ===

$scenarios = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name

foreach ($scenario in (@($null) + $scenarios)) {

    $label = if ($null -eq $scenario) { "baseline" } else { $scenario }
    Write-Host "=== engine : $label ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $scenario

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec engine pour $label (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
