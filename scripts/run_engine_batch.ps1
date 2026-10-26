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
La baseline Base_year_2015 est ecrite dans Module_PlaneFR\data\<Version>\no_SSP,
puis copiee dans chaque autre groupe (SSP1_2050...) pour y servir de scenario
de reference ; la baseline 2019 reste dans Module_PlaneFR\data\<Version>\2019_FR.
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
# Le path_out initial peut etre "...\data\<version>\<scenario>" ou, apres un
# run de scenario, "...\data\<version>\<groupe>\<scenario>" : on coupe donc au
# dossier de version plutot que de remonter d'un nombre fixe de niveaux.
$engineOutDataDir = [regex]::Replace($initialSettings.path_out, "\\\d+\.\d+\.\d+(\\.*)?$", "")
$engineOutBaseDir = Join-Path $engineOutDataDir $Version

# Dossier contenant les accounts France (ex. ".\4-PlaneFR\Outputs\France") :
# fixe ici plutot que deduit du JSON, dont path_in.accounts change a chaque run
$accountsBaseDir = ".\4-PlaneFR\Outputs\France"

# Dossier d'accounts dont les sorties de scenario vont dans "no_SSP"
$noSspAccountsName = "Base_year_2015"

# Sortie baseline copiee dans chaque dossier de groupe (no_SSP, SSP1_2050...),
# pour servir de scenario de reference aux figures de Module_PlaneFR
$referenceBaselineName = "Base_year_2015"

function Get-ScenarioGroup {
    param(
        # Nom du dossier d'accounts (ex. "Base_year_2015" ou "SSP2_2050")
        [string]$AccountsName
    )
    if ($AccountsName -eq $noSspAccountsName) {
        return "no_SSP"
    }
    return $AccountsName
}

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
        elseif ("Base_year_$Year" -eq $referenceBaselineName) {
            # Baseline de reference : ecrite dans le groupe no_SSP, puis copiee
            # dans les autres groupes (cf. fin de la boucle des scenarios)
            $settings.path_out = Join-Path (Join-Path $outBaseDir (Get-ScenarioGroup -AccountsName $noSspAccountsName)) "Base_year_$Year"
        }
        else {
            $settings.path_out = Join-Path $outBaseDir "Base_year_$Year"
        }
    }
    else {
        $group = Get-ScenarioGroup -AccountsName $AccountsName
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

    # === Copie de la baseline de reference (ecrite dans no_SSP) dans le
    # dossier du groupe ===
    $group = Get-ScenarioGroup -AccountsName $accountsName
    if ($accountsName -eq $noSspAccountsName) {
        continue
    }
    $baseline  = Join-Path (Join-Path $engineOutBaseDir (Get-ScenarioGroup -AccountsName $noSspAccountsName)) $referenceBaselineName
    $groupCopy = Join-Path (Join-Path $engineOutBaseDir $group) $referenceBaselineName

    if (-not (Test-Path (Join-Path $baseline "extensions"))) {
        Write-Host "Copie de $referenceBaselineName dans $group impossible : $baseline introuvable ou incomplet" -ForegroundColor Red
        continue
    }
    Write-Host "--- $group : copie de $baseline ---" -ForegroundColor Cyan
    if (Test-Path $groupCopy) {
        Remove-Item -Path $groupCopy -Recurse -Force
    }
    Copy-Item -Path $baseline -Destination $groupCopy -Recurse
}
