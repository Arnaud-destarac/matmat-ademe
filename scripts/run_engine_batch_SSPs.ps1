<#
Chains the engine step for each SSP scenario present in
data\4-PlaneFR\2-shocks\3-SSPs_2050, adapting the paths (path_in.shock
and path_out) in settings_engine_SSPs.json before each run.

path_in.accounts is kept as is (e.g. Outputs\World\Base_year_2015): these are
the base World accounts of the SSP scenarios. generate_shock_dS.py and
generate_shock_agri.py read this same path to build the shocks
(structure of the dS and dA, detail_levels, base_year); to change the base
year, edit path_in.accounts in settings_engine_SSPs.json then rerun
these scripts (run_all_SSPs.ps1).
The outputs are written to the parent folder of the initial path_out
(e.g. .\4-PlaneFR\Outputs\World\<scenario>).

-Suffix (e.g. "_agri"): reads the shocks in 3-SSPs_2050<Suffix> and ensures
that every output folder ends with <Suffix>.
#>

param(
    # Suffix of the shock and output folders ("" by default, e.g. "_agri")
    [string]$Suffix = ""
)

$projectDir = Split-Path -Parent $PSScriptRoot

$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_SSPs.json"
$shocksDir          = Join-Path $projectDir "data\4-PlaneFR\2-shocks\3-SSPs_2050$Suffix"

function Add-Suffix {
    param([string]$Name)
    # Appends $Suffix to the name unless it already ends with it
    if ($Name.EndsWith($Suffix)) { return $Name }
    return "$Name$Suffix"
}

Set-Location $projectDir

# Base output folder (e.g. ".\4-PlaneFR\Outputs\World"): parent folder of the
# initial path_out (".\4-PlaneFR\Outputs\World\<scenario>").
$initialSettings  = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
$engineOutBaseDir = Split-Path -Parent $initialSettings.path_out

function Set-EngineSettings {
    param(
        # Name of the scenario sub-folder (e.g. "SSP2_2050")
        [string]$ScenarioName
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    $settings.path_in.shock = ".\4-PlaneFR\2-shocks\3-SSPs_2050$Suffix\$ScenarioName"
    $settings.path_out      = Join-Path $engineOutBaseDir (Add-Suffix $ScenarioName)

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === Engine step: one run per scenario present in
# data\4-PlaneFR\2-shocks\3-SSPs_2050 ===

$scenarios = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name

foreach ($scenario in $scenarios) {
    Write-Host "=== engine : $scenario ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $scenario

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Engine failed for $scenario (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
