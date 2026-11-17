<#
Chains the gmrio_to_snac_s step for each base year (2015, 2019),
for the Exiobase version passed as a parameter (-Version, 3.11.2 by
default), adapting the paths (year, version) in the JSON settings file
before each run.

Then rebuilds the "extensions" sub-folders of each scenario of
data\4-PlaneFR\2-shocks\1-transitions_2050 (dom_<ext> for each
extension_name of gmrio_to_snac_s, with detail_levels.xlsx and info.json).
The dS_x_dom shocks already present (compute_ds_x_dom.py) are kept, so
that the engine applies them from the first pass (see
rebuild_shock_extensions.py).

To be run from the matmat-ademe environment (pipeline carried in
src/matmat/workflows/pipelines/accounts/gmrio_to_snac_s).
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

$projectDir = Split-Path -Parent $PSScriptRoot

$gmrioSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\2-gmrio_to_snac_s\gmrio_to_snac_S_FR.json"

$baseYears = 2015, 2019
$versions  = $Version

Set-Location $projectDir

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Replaces every "_20xx" (year) occurrence by "_$Year", so that the
    # version_year folder and the version_pxp_year sub-folder stay
    # consistent with each other.
    return [regex]::Replace($Path, "_20\d{2}", "_$Year")
}

function Set-VersionInPath {
    param(
        [string]$Path,
        [string]$Version
    )
    # Replaces every Exiobase version number (e.g. 3.10.2, 3.9.6) by the
    # requested version, leaving the rest of the path (year, sub-folders)
    # unchanged.
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
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($gmrioSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($year in $baseYears) {
    foreach ($version in $versions) {
        Write-Host "=== base_year=$year / version=$version : gmrio_to_snac_s ===" -ForegroundColor Cyan

        Set-GmrioToSnacSSettings -Year $year -Version $version

        uv run python -m matmat.cli -p gmrio_to_snac_s -st $gmrioSettingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "gmrio_to_snac_s failed for base_year=$year / version=$version (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }
}

# === Rebuilding the "extensions" folders of the shock scenarios ===
# For each scenario of $shocksDir, empties the "extensions" sub-folder (keeping
# the dS_x_dom) then recreates it with one dom_<ext> folder per extension_name of
# gmrio_to_snac_s, containing the matching detail_levels.xlsx and info.json
# (see rebuild_shock_extensions.py). The gmrio_to_snac_s output used is
# that of the base_year of the scenario (system\info.json) and of the
# $Version version.
$shocksDir = Join-Path $projectDir "data\4-PlaneFR\2-shocks\1-transitions_2050"
$dataDir   = Join-Path $projectDir "data"

Write-Host "=== Rebuilding the shock extensions ($shocksDir) ===" -ForegroundColor Cyan

$settings       = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json
$extensionNames = @($settings.extension_names)
$failed         = $false

foreach ($scenarioDir in Get-ChildItem -Path $shocksDir -Directory) {
    $systemInfoPath = Join-Path $scenarioDir.FullName "system\info.json"
    if (-not (Test-Path $systemInfoPath)) {
        Write-Host "Scenario $($scenarioDir.Name) skipped: $systemInfoPath not found" -ForegroundColor Yellow
        continue
    }
    $baseYear = [int](Get-Content -Raw -Path $systemInfoPath | ConvertFrom-Json).base_year

    $gmrioOutDir = Join-Path $dataDir (Set-YearInPath -Path $settings.path_out -Year $baseYear)
    $missing = $extensionNames | Where-Object {
        -not (Test-Path (Join-Path $gmrioOutDir "extensions\dom_$_\detail_levels.xlsx"))
    }
    if ($missing) {
        # Nothing is deleted if the gmrio_to_snac_s output is incomplete
        Write-Host "Scenario $($scenarioDir.Name) skipped: extensions missing from $gmrioOutDir : $($missing -join ', ')" -ForegroundColor Red
        $failed = $true
        continue
    }

    # The cleaning of the extensions folder (except dS_*) is done by the Python script
    uv run python (Join-Path $PSScriptRoot "rebuild_shock_extensions.py") `
        --scenario-dir $scenarioDir.FullName `
        --gmrio-dir $gmrioOutDir `
        --extensions $extensionNames

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Rebuilding the extensions failed for $($scenarioDir.Name) (code $LASTEXITCODE)" -ForegroundColor Red
        $failed = $true
    }
}

if ($failed) {
    exit 1
}
