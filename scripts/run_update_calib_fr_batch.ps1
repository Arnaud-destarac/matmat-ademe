<#
Chains the update_calib_fr step for each base year (2015, 2019), adapting
the paths (year) in the JSON settings file before each run.

The "update_calib_fr" pipeline is not (yet) ported to matmat-ademe
(src/matmat/workflows/pipelines/accounts/ only contains "aggregation" and
"gmrio_to_snac_s"; -p update_calib_fr does not exist in its cli.py). It only
exists in the old wheel installed for the datapack project
(matmat==0.9.0b0). This script therefore edits the settings file located in
matmat-ademe, but runs the command from the datapack folder (sibling of
matmat-ademe), to use its environment/CLI.

The Exiobase version (-Version, 3.11.2 by default) is written into the
newer_accounts path (gmrio_to_snac_s output); older_accounts (reference
France accounts) is not modified.
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

# Paths computed relative to the location of this script, so that the
# script works whatever the current directory it is invoked from.
$matmatAdemeDir = Split-Path -Parent $PSScriptRoot
$matmatRootDir  = Split-Path -Parent $matmatAdemeDir
$datapackDir    = Join-Path $matmatRootDir "datapack"

$calibSettingsPath = Join-Path $matmatAdemeDir "data\4-PlaneFR\Settings\3-update_calib_fr\update_calib_fr_PlaneFR.json"

$baseYears = 2015, 2019

function Set-YearInPath {
    param(
        [string]$Path,
        [int]$Year
    )
    # Replaces the last "_20xx" (year) occurrence by "_$Year", leaving the
    # rest of the path (version, sub-folders) unchanged.
    return [regex]::Replace($Path, "_20\d{2}(?!.*_20\d{2})", "_$Year")
}

function Set-VersionInPath {
    param(
        [string]$Path,
        [string]$Version
    )
    # Replaces every Exiobase version number (e.g. 3.10.2) by the requested
    # version, leaving the rest of the path unchanged.
    return [regex]::Replace($Path, "\d+\.\d+\.\d+", $Version)
}

function Set-UpdateCalibFrSettings {
    param(
        [int]$Year
    )

    $settings = Get-Content -Raw -Path $calibSettingsPath | ConvertFrom-Json

    $settings.path_in.newer_accounts = Set-YearInPath -Path $settings.path_in.newer_accounts -Year $Year
    $settings.path_in.newer_accounts = Set-VersionInPath -Path $settings.path_in.newer_accounts -Version $Version
    $settings.path_in.older_accounts = Set-YearInPath -Path $settings.path_in.older_accounts -Year $Year
    $settings.path_out                = Set-YearInPath -Path $settings.path_out -Year $Year

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($calibSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

Set-Location $datapackDir

foreach ($year in $baseYears) {
    Write-Host "=== base_year=$year : update_calib_fr ===" -ForegroundColor Cyan

    Set-UpdateCalibFrSettings -Year $year

    uv run python -m matmat.cli -p update_calib_fr -st $calibSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "update_calib_fr failed for base_year=$year (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
