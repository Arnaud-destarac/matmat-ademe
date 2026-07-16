<#
Enchaine l'etape engine (baseline + un run par scenario) en adaptant les
chemins dans le fichier de settings JSON avant chaque run.

Suppose que les etapes gmrio_to_snac_s et update_calib_fr ont deja ete
executees au prealable (cf. run_calib_fr_batch.ps1 / run_update_calib_fr_batch.ps1)
et que leurs sorties sont disponibles.
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_France_shocks.json"
$shocksDir          = Join-Path $projectDir "data\3-workshops\2-shocks\1-transitions_2050"

Set-Location $projectDir

# Dossier de sortie de base (ex. "...\Module_PlaneFR\data\3.10.2"), capture
# une seule fois depuis le path_out initial pour ne pas deriver d'une valeur
# deja ecrasee par une iteration precedente.
$initialSettings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
$engineOutBaseDir = Split-Path -Parent $initialSettings.path_out

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Remplace la derniere occurrence "_20xx" (annee) par "_$Year", en
    # conservant le reste du chemin (version, sous-dossiers) inchange.
    return [regex]::Replace($Path, "_20\d{2}(?!.*_20\d{2})", "_$Year")
}

function Set-EngineSettings {
    param(
        # $null pour un run baseline (pas de choc), sinon nom du sous-dossier
        # de scenario (ex. "S1_2050"). Pas de type [string] ici : PowerShell
        # convertirait silencieusement un $null passe en argument en "",
        # ce qui casserait le test $null -eq $ScenarioName ci-dessous.
        $ScenarioName,
        # Annee de base des accounts (utilisee uniquement pour les runs
        # baseline ; les scenarios utilisent l'annee deja presente dans le
        # fichier de settings, Base_year_2015).
        [int]$Year = 2015
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    $outBaseDir = $engineOutBaseDir

    if ($null -eq $ScenarioName) {
        $settings.path_in.accounts = Set-YearInPath -Path $settings.path_in.accounts -Year $Year
        $settings.path_in.shock    = $null
        if ($Year -eq 2019) {
            $settings.path_out = Join-Path $outBaseDir "2019_France"
        }
        else {
            $settings.path_out = Join-Path $outBaseDir "Base_year_$Year"
        }
    }
    else {
        # path_in.accounts fixe a Base_year_2015, quel que soit l'ordre des
        # runs baseline precedents
        $settings.path_in.accounts = Set-YearInPath -Path $settings.path_in.accounts -Year 2015
        $settings.path_in.shock    = ".\3-workshops\2-shocks\1-transitions_2050\$ScenarioName"
        $settings.path_out         = Join-Path $outBaseDir $ScenarioName
    }

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === Etape engine : baseline 2015, baseline 2019, puis un run par scenario
# present dans data\3-workshops\2-shocks\1-transitions_2050 ===

$baselineYears = 2015, 2019
$scenarios     = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name

foreach ($year in $baselineYears) {
    Write-Host "=== engine : baseline Base_year_$year ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $null -Year $year

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec engine pour baseline Base_year_$year (code $LASTEXITCODE)" -ForegroundColor Red
    }
}

foreach ($scenario in $scenarios) {
    Write-Host "=== engine : $scenario ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $scenario

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec engine pour $scenario (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
