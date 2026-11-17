<#
Chains the engine step for each SSP scenario present in
data\4-PlaneFR\2-shocks\3-SSPs_2050, adapting the paths (path_in.shock
and path_out) of the settings template
planeFR\parameters\4-engine\settings_engine_SSPs.json before each run (see
planefr_common.ps1).

path_in.accounts is kept as is (e.g. Outputs\World\Base_year_2015): these are
the base World accounts of the SSP scenarios. generate_shock_dS.py and
generate_shock_agri.py read this same path in the template to build the shocks
(structure of the dS and dA, detail_levels, base_year); to change the base
year, edit path_in.accounts in the template then rerun these scripts
(run_all_SSPs.ps1).
The outputs are written to the parent folder of the path_out of the template
(e.g. .\4-PlaneFR\Outputs\World\<scenario>).

-Suffix (e.g. "_agri"): reads the shocks in 3-SSPs_2050<Suffix> and ensures
that every output folder ends with <Suffix>.
#>

param(
    # Suffix of the shock and output folders ("" by default, e.g. "_agri")
    [string]$Suffix = ""
)

. (Join-Path $PSScriptRoot "..\_common\planefr_common.ps1")

$projectDir = $MatmatAdemeDir

# Template planeFR\parameters\4-engine\settings_engine_SSPs.json
$engineTemplate = "4-engine\settings_engine_SSPs.json"
$shocksDir         = Join-Path $projectDir "data\4-PlaneFR\2-shocks\3-SSPs_2050$Suffix"

function Add-Suffix {
    param([string]$Name)
    # Appends $Suffix to the name unless it already ends with it
    if ($Name.EndsWith($Suffix)) { return $Name }
    return "$Name$Suffix"
}

Set-Location $projectDir

# Base output folder (e.g. ".\4-PlaneFR\Outputs\World"): parent folder of the
# path_out of the template (".\4-PlaneFR\Outputs\World\<scenario>").
$initialSettings  = Read-SettingsTemplate $engineTemplate
$engineOutBaseDir = Split-Path -Parent $initialSettings.path_out

function New-EngineSettings {
    param(
        # Name of the scenario sub-folder (e.g. "SSP2_2050")
        [string]$ScenarioName
    )

    $settings = Read-SettingsTemplate $engineTemplate

    $settings.path_in.shock = ".\4-PlaneFR\2-shocks\3-SSPs_2050$Suffix\$ScenarioName"
    $settings.path_out      = Join-Path $engineOutBaseDir (Add-Suffix $ScenarioName)

    return Write-RunSettings $engineTemplate $settings
}

# === Engine step: one run per scenario present in
# data\4-PlaneFR\2-shocks\3-SSPs_2050 ===

$scenarios = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name

# A failed run does not stop the loop, but the script ends with exit code 1
$failed = $false

foreach ($scenario in $scenarios) {
    Write-Host "=== engine : $scenario ===" -ForegroundColor Cyan

    $engineSettingsPath = New-EngineSettings -ScenarioName $scenario

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Engine failed for $scenario (code $LASTEXITCODE)" -ForegroundColor Red
        $failed = $true
    }
}

if ($failed) {
    Write-Host "run_engine_batch_SSPs.ps1: at least one run failed (see above)" -ForegroundColor Red
    exit 1
}
exit 0
