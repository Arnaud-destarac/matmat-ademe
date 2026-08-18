<#
Lance plusieurs fois la commande exiobase3_eeio en faisant varier
base_year et version dans le fichier de settings JSON.
#>

$projectDir   = Split-Path -Parent $PSScriptRoot
$settingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\1-exiobase3_eeio\exiobase3_eeio_settings.json"

$baseYears = 2015, 2019
$versions  = "3.9.6", "3.10.2"

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
    # Ecriture en UTF-8 sans BOM pour eviter les erreurs de parsing JSON cote Python
    [System.IO.File]::WriteAllText($settingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($baseYear in $baseYears) {
    foreach ($version in $versions) {
        Write-Host "=== base_year=$baseYear / version=$version ===" -ForegroundColor Cyan

        Set-JsonValueAndSave -BaseYear $baseYear -Version $version

        uv run python -m matmat.cli -a exiobase3_eeio -st $settingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Echec pour base_year=$baseYear / version=$version (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }
}

# Remplace F_x_dom.pkl (extension water) de la version 3.10.2 par celui de la version 3.9.6,
# pour chaque base_year traite.
foreach ($baseYear in $baseYears) {
    $sourceFile = Join-Path $projectDir "data\4-PlaneFR\1-accounts\Exiobase\3.9.6_${baseYear}\3.9.6_pxp_${baseYear}\extensions\water\F_x_dom.pkl"
    $destFile   = Join-Path $projectDir "data\4-PlaneFR\1-accounts\Exiobase\3.10.2_${baseYear}\3.10.2_pxp_${baseYear}\extensions\water\F_x_dom.pkl"

    if (Test-Path $sourceFile) {
        Copy-Item -Path $sourceFile -Destination $destFile -Force
        Write-Host "F_x_dom.pkl (water) copie de 3.9.6 vers 3.10.2 pour base_year=$baseYear" -ForegroundColor Green
    } else {
        Write-Host "Fichier source introuvable pour base_year=$baseYear : $sourceFile" -ForegroundColor Red
    }
}

# Remplace F_x_dom.pkl (extension energy) de la version 3.10.2 par celui de la version 3.9.6,
# pour chaque base_year traite.
foreach ($baseYear in $baseYears) {
    $sourceFile = Join-Path $projectDir "data\4-PlaneFR\1-accounts\Exiobase\3.9.6_${baseYear}\3.9.6_pxp_${baseYear}\extensions\energy\F_x_dom.pkl"
    $destFile   = Join-Path $projectDir "data\4-PlaneFR\1-accounts\Exiobase\3.10.2_${baseYear}\3.10.2_pxp_${baseYear}\extensions\energy\F_x_dom.pkl"

    if (Test-Path $sourceFile) {
        Copy-Item -Path $sourceFile -Destination $destFile -Force
        Write-Host "F_x_dom.pkl (energy) copie de 3.9.6 vers 3.10.2 pour base_year=$baseYear" -ForegroundColor Green
    } else {
        Write-Host "Fichier source introuvable pour base_year=$baseYear : $sourceFile" -ForegroundColor Red
    }
}

# Lance le moteur eeio (uniquement pour la version 3.10.2), en adaptant
# path_in et path_out a chaque base_year dans settings_engine_World.json.
$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_World.json"
$engineVersion = "3.10.2"

function Set-EngineJsonValueAndSave {
    param(
        [int]$BaseYear
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
    $settings.path_in.accounts = ".\4-PlaneFR\1-accounts\Exiobase\${engineVersion}_${BaseYear}\${engineVersion}_pxp_${BaseYear}"
    $settings.path_out          = ".\4-PlaneFR\Outputs\World\base-year_${BaseYear}"

    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

foreach ($baseYear in $baseYears) {
    Write-Host "=== eeio: base_year=$baseYear / version=$engineVersion ===" -ForegroundColor Cyan

    Set-EngineJsonValueAndSave -BaseYear $baseYear

    uv run -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Echec eeio pour base_year=$baseYear (code $LASTEXITCODE)" -ForegroundColor Red
    }
}
