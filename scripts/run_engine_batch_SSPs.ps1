<#
Enchaine l'etape engine pour chaque scenario SSP present dans
data\4-PlaneFR\2-shocks\3-SSPs_2050, en adaptant les chemins (path_in.shock
et path_out) dans settings_engine_SSPs.json avant chaque run.

path_in.accounts est conserve tel quel (ex. Outputs\World\Base_year_2019).
Les sorties sont ecrites dans le dossier parent du path_out initial
(ex. .\4-PlaneFR\Outputs\World\<scenario>).
#>

$projectDir = Split-Path -Parent $PSScriptRoot

$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_SSPs.json"
$shocksDir          = Join-Path $projectDir "data\4-PlaneFR\2-shocks\3-SSPs_2050"

Set-Location $projectDir

# Dossier de sortie de base (ex. ".\4-PlaneFR\Outputs\World") : dossier
# parent du path_out initial (".\4-PlaneFR\Outputs\World\<scenario>").
$initialSettings  = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
$engineOutBaseDir = Split-Path -Parent $initialSettings.path_out

function Set-EngineSettings {
    param(
        # Nom du sous-dossier de scenario (ex. "SSP2_2050")
        [string]$ScenarioName
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    $settings.path_in.shock = ".\4-PlaneFR\2-shocks\3-SSPs_2050\$ScenarioName"
    $settings.path_out      = Join-Path $engineOutBaseDir $ScenarioName

    $json = $settings | ConvertTo-Json -Depth 10
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === Etape engine : un run par scenario present dans
# data\4-PlaneFR\2-shocks\3-SSPs_2050 ===

$scenarios = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name

foreach ($scenario in $scenarios) {
    Write-Host "=== engine : $scenario ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $scenario

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec engine pour $scenario (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
