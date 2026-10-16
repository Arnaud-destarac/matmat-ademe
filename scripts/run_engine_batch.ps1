<#
Enchaine l'etape engine (baseline + un run par couple accounts/scenario) en
adaptant les chemins dans le fichier de settings JSON avant chaque run.

Suppose que les etapes gmrio_to_snac_s et update_calib_fr ont deja ete
executees au prealable (cf. run_calib_fr_batch.ps1 / run_update_calib_fr_batch.ps1
/ run_update_calib_fr_batch_SSPs.ps1) et que leurs sorties sont disponibles.

Les runs de scenario iterent sur chaque dossier d'accounts present dans
data\4-PlaneFR\Outputs\France (hors dossiers contenant "2019") et sur chaque
scenario de data\4-PlaneFR\2-shocks\1-transitions_2050. Les sorties sont
ecrites dans Module_PlaneFR\data\<Version>\<groupe>\<scenario> (-Version,
3.11.2 par defaut), avec <groupe> = "no_SSP" pour les accounts
Base_year_2015, et le nom du dossier d'accounts sinon (ex. "SSP2_2050").
Les baselines restent ecrites dans Module_PlaneFR\data\<Version>.
#>

param(
    # Version Exiobase a utiliser (ex. "3.11.2")
    [string]$Version = "3.11.2"
)

$projectDir = Split-Path -Parent $PSScriptRoot

$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_France_shocks.json"
$shocksDir          = Join-Path $projectDir "data\4-PlaneFR\2-shocks\1-transitions_2050"

Set-Location $projectDir

# Dossier de sortie de base (ex. "...\Module_PlaneFR\data\3.11.2") : dossier
# data du path_out initial ("...\data\<version>\<scenario>"), suivi de la
# version demandee.
$initialSettings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
$engineOutBaseDir = Join-Path (Split-Path -Parent (Split-Path -Parent $initialSettings.path_out)) $Version

# Dossier contenant les accounts France (ex. ".\4-PlaneFR\Outputs\France") :
# fixe ici plutot que deduit du JSON, dont path_in.accounts change a chaque run
$accountsBaseDir = ".\4-PlaneFR\Outputs\France"

# Dossier d'accounts dont les sorties de scenario vont dans "no_SSP"
$noSspAccountsName = "Base_year_2015"

function Set-EngineSettings {
    param(
        # $null pour un run baseline (pas de choc), sinon nom du sous-dossier
        # de scenario (ex. "S1_2050"). Pas de type [string] ici : PowerShell
        # convertirait silencieusement un $null passe en argument en "",
        # ce qui casserait le test $null -eq $ScenarioName ci-dessous.
        $ScenarioName,
        # Annee de base des accounts (utilisee uniquement pour les runs
        # baseline).
        [int]$Year = 2015,
        # Nom du dossier d'accounts dans $accountsBaseDir (utilise uniquement
        # pour les runs de scenario, ex. "Base_year_2015" ou "SSP2_2050").
        [string]$AccountsName = $noSspAccountsName
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    $outBaseDir = $engineOutBaseDir

    if ($null -eq $ScenarioName) {
        $settings.path_in.accounts = Join-Path $accountsBaseDir "Base_year_$Year"
        $settings.path_in.shock    = $null
        if ($Year -eq 2019) {
            $settings.path_out = Join-Path $outBaseDir "2019_FR"
        }
        else {
            $settings.path_out = Join-Path $outBaseDir "Base_year_$Year"
        }
    }
    else {
        if ($AccountsName -eq $noSspAccountsName) {
            $group = "no_SSP"
        }
        else {
            $group = $AccountsName
        }
        $settings.path_in.accounts = Join-Path $accountsBaseDir $AccountsName
        $settings.path_in.shock    = ".\4-PlaneFR\2-shocks\1-transitions_2050\$ScenarioName"
        $settings.path_out         = Join-Path (Join-Path $outBaseDir $group) $ScenarioName
    }

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === Etape engine : baseline 2015, baseline 2019, puis un run par couple
# (dossier d'accounts de data\4-PlaneFR\Outputs\France hors "2019",
# scenario de data\4-PlaneFR\2-shocks\1-transitions_2050) ===

$baselineYears = 2015, 2019
$scenarios     = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name
$accountsNames = Get-ChildItem -Path (Join-Path $projectDir "data\$accountsBaseDir") -Directory |
    Where-Object { $_.Name -notmatch "2019" } |
    Select-Object -ExpandProperty Name

foreach ($year in $baselineYears) {
    Write-Host "=== engine : baseline Base_year_$year ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $null -Year $year

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec engine pour baseline Base_year_$year (code $LASTEXITCODE)" -ForegroundColor Red
    }
}

foreach ($accountsName in $accountsNames) {
    foreach ($scenario in $scenarios) {
        Write-Host "=== engine : $accountsName / $scenario ===" -ForegroundColor Cyan

        Set-EngineSettings -ScenarioName $scenario -AccountsName $accountsName

        uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Echec engine pour $accountsName / $scenario (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }
}
