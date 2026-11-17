<#
Runs the exiobase3_eeio command several times, varying base_year and version
in the settings (template planeFR\parameters\1-exiobase3_eeio\exiobase3_eeio_settings.json),
then runs the eeio engine on the World accounts of each base year (template
planeFR\parameters\4-engine\settings_engine_World.json).

The Exiobase version is passed as a parameter (-Version, 3.11.2 by default).
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

. (Join-Path $PSScriptRoot "..\_common\planefr_common.ps1")

$adapterTemplate = "1-exiobase3_eeio\exiobase3_eeio_settings.json"
$engineTemplate  = "4-engine\settings_engine_World.json"

$baseYears = 2015, 2019
$versions  = $Version

Set-Location $MatmatAdemeDir

# A failed run does not stop the loops, but the script ends with exit code 1
$failed = $false

function New-AdapterSettings {
    param(
        [int]$BaseYear,
        [string]$Version
    )

    $settings = Read-SettingsTemplate $adapterTemplate
    $settings.base_year = $BaseYear
    $settings.version   = $Version
    $settings.path_out  = ".\4-PlaneFR\1-accounts\Exiobase\${Version}_${BaseYear}"

    return Write-RunSettings $adapterTemplate $settings
}

foreach ($baseYear in $baseYears) {
    foreach ($version in $versions) {
        Write-Host "=== base_year=$baseYear / version=$version ===" -ForegroundColor Cyan

        $settingsPath = New-AdapterSettings -BaseYear $baseYear -Version $version

        uv run python -m matmat.cli -a exiobase3_eeio -st $settingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed for base_year=$baseYear / version=$version (code $LASTEXITCODE)" -ForegroundColor Red
            $failed = $true
        }
    }
}

# Runs the eeio engine (for version $Version), adapting path_in and path_out
# to each base_year.
$engineVersion = $Version

function New-EngineSettings {
    param(
        [int]$BaseYear
    )

    $settings = Read-SettingsTemplate $engineTemplate
    $settings.path_in.accounts = ".\4-PlaneFR\1-accounts\Exiobase\${engineVersion}_${BaseYear}\${engineVersion}_pxp_${BaseYear}"
    $settings.path_out          = ".\4-PlaneFR\Outputs\World\Base_year_${BaseYear}"

    return Write-RunSettings $engineTemplate $settings
}

foreach ($baseYear in $baseYears) {
    Write-Host "=== eeio: base_year=$baseYear / version=$engineVersion ===" -ForegroundColor Cyan

    $engineSettingsPath = New-EngineSettings -BaseYear $baseYear

    uv run -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "eeio failed for base_year=$baseYear (code $LASTEXITCODE)" -ForegroundColor Red
        $failed = $true
    }
}

if ($failed) {
    Write-Host "run_exiobase3_eeio_batch.ps1: at least one run failed (see above)" -ForegroundColor Red
    exit 1
}
exit 0
