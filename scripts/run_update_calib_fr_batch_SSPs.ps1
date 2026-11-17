<#
Chains the update_calib_fr step for each scenario present in
data\4-PlaneFR\Outputs_inter\gmrio_to_snac_s\SSPs (gmrio_to_snac_s outputs,
see run_gmrio_to_snac_s_batch_SSPs.ps1), adapting the paths in the JSON
settings file before each run:
- newer_accounts: scenario folder if it directly contains system\
  (e.g. Base_year_2015), otherwise its <Version>_pxp_<year> sub-folder
  (e.g. SSP1_2050\3.11.2_pxp_2019);
- older_accounts: year replaced by the base_year of the scenario (read in
  system\info.json), e.g. 3.10.2_France_2015 or 3.10.2_France_2019;
- path_out: .\4-PlaneFR\Outputs\France\<scenario>.

The "update_calib_fr" pipeline is not (yet) ported to matmat-ademe
(src/matmat/workflows/pipelines/accounts/ only contains "aggregation" and
"gmrio_to_snac_s"; -p update_calib_fr does not exist in its cli.py). It only
exists in the old wheel installed for the datapack project
(matmat==0.9.0b0). This script therefore edits the settings file located in
matmat-ademe, but runs the command from the datapack folder (sibling of
matmat-ademe), to use its environment/CLI.

-Suffix (e.g. "_agri"): reads Outputs_inter\gmrio_to_snac_s\SSPs<Suffix> and
writes to Outputs\France<Suffix>.
#>

param(
    # Exiobase version to use (e.g. "3.11.2"): selects the
    # <Version>_pxp_<year> sub-folder of the scenarios that have one
    [string]$Version = "3.11.2",
    # Suffix of the input and output folders ("" by default, e.g. "_agri")
    [string]$Suffix = ""
)

# Paths computed relative to the location of this script, so that the
# script works whatever the current directory it is invoked from.
$matmatAdemeDir = Split-Path -Parent $PSScriptRoot
$matmatRootDir  = Split-Path -Parent $matmatAdemeDir
$datapackDir    = Join-Path $matmatRootDir "datapack"

$calibSettingsPath = Join-Path $matmatAdemeDir "data\4-PlaneFR\Settings\3-update_calib_fr\update_calib_fr_PlaneFR_SSPs.json"

# The paths of the settings are relative to the data folder
$dataDir = Join-Path $matmatAdemeDir "data"

# Paths (relative to data) of the gmrio_to_snac_s outputs by scenario and of the
# update_calib_fr outputs
$newerBaseDir = ".\4-PlaneFR\Outputs_inter\gmrio_to_snac_s\SSPs$Suffix"
$outBaseDir   = ".\4-PlaneFR\Outputs\France$Suffix"

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Replaces the last "_20xx" (year) occurrence by "_$Year", leaving the
    # rest of the path (version, sub-folders) unchanged.
    return [regex]::Replace($Path, "_20\d{2}(?!.*_20\d{2})", "_$Year")
}

function Get-NewerAccountsDir {
    param(
        # Scenario folder (absolute path)
        [string]$ScenarioDir
    )
    # Returns the path (relative to the scenario folder) of the
    # gmrio_to_snac_s accounts: "" if system\ is directly in the scenario,
    # otherwise the <Version>_pxp_<year> sub-folder containing system\. $null if
    # none is found.
    if (Test-Path (Join-Path $ScenarioDir "system\info.json")) {
        return ""
    }
    $sub = Get-ChildItem -Path $ScenarioDir -Directory -Filter "$($Version)_pxp_*" |
        Where-Object { Test-Path (Join-Path $_.FullName "system\info.json") } |
        Select-Object -First 1
    if ($null -eq $sub) {
        return $null
    }
    return $sub.Name
}

function Set-UpdateCalibFrSettings {
    param(
        [string]$NewerAccounts,
        [string]$PathOut,
        [int]$Year
    )

    $settings = Get-Content -Raw -Path $calibSettingsPath | ConvertFrom-Json

    $settings.path_in.newer_accounts = $NewerAccounts
    $settings.path_in.older_accounts = Set-YearInPath -Path $settings.path_in.older_accounts -Year $Year
    $settings.path_out               = $PathOut

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($calibSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === update_calib_fr step: one run per scenario present in
# data\4-PlaneFR\Outputs_inter\gmrio_to_snac_s\SSPs ===

$scenarioDirs = Get-ChildItem -Path (Join-Path $dataDir $newerBaseDir) -Directory

Set-Location $datapackDir

foreach ($scenarioDir in $scenarioDirs) {
    $scenario = $scenarioDir.Name

    $sub = Get-NewerAccountsDir -ScenarioDir $scenarioDir.FullName
    if ($null -eq $sub) {
        Write-Host "Scenario $scenario skipped: no system\info.json (nor in a $($Version)_pxp_* sub-folder)" -ForegroundColor Yellow
        continue
    }

    $newerAccounts = Join-Path $newerBaseDir $scenario
    if ($sub) {
        $newerAccounts = Join-Path $newerAccounts $sub
    }

    $systemInfoPath = Join-Path $dataDir (Join-Path $newerAccounts "system\info.json")
    $baseYear       = [int](Get-Content -Raw -Path $systemInfoPath | ConvertFrom-Json).base_year

    Write-Host "=== $scenario (base_year=$baseYear) : update_calib_fr ===" -ForegroundColor Cyan

    Set-UpdateCalibFrSettings -NewerAccounts $newerAccounts -PathOut (Join-Path $outBaseDir $scenario) -Year $baseYear

    uv run python -m matmat.cli -p update_calib_fr -st $calibSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "update_calib_fr failed for $scenario (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
