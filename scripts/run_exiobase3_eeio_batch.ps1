<#
Runs the exiobase3_eeio command several times, varying
base_year and version in the JSON settings file.

The Exiobase version is passed as a parameter (-Version, 3.11.2 by default).
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

$projectDir   = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\1-exiobase3_eeio\exiobase3_eeio_settings.json"

$baseYears = 2015, 2019
$versions  = $Version

Set-Location $projectDir

function Set-JsonValueAndSave {
    param(
        [int]$BaseYear,
        [string]$Version
    )

    $settings = Get-Content -Raw -Path $settingsPath | ConvertFrom-Json
    $settings.base_year = $BaseYear
    $settings.version   = $Version
    $settings.path_out  = ".\4-PlaneFR\1-accounts\Exiobase\${Version}_${BaseYear}"

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($settingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($baseYear in $baseYears) {
    foreach ($version in $versions) {
        Write-Host "=== base_year=$baseYear / version=$version ===" -ForegroundColor Cyan

        Set-JsonValueAndSave -BaseYear $baseYear -Version $version

        uv run python -m matmat.cli -a exiobase3_eeio -st $settingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed for base_year=$baseYear / version=$version (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }
}

# to be inserted if needed

# Runs the eeio engine (for version $Version), adapting
# path_in and path_out to each base_year in settings_engine_World.json.
$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_World.json"
$engineVersion = $Version

function Set-EngineJsonValueAndSave {
    param(
        [int]$BaseYear
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
    $settings.path_in.accounts = ".\4-PlaneFR\1-accounts\Exiobase\${engineVersion}_${BaseYear}\${engineVersion}_pxp_${BaseYear}"
    $settings.path_out          = ".\4-PlaneFR\Outputs\World\Base_year_${BaseYear}"

    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($baseYear in $baseYears) {
    Write-Host "=== eeio: base_year=$baseYear / version=$engineVersion ===" -ForegroundColor Cyan

    Set-EngineJsonValueAndSave -BaseYear $baseYear

    uv run -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "eeio failed for base_year=$baseYear (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
