<#
Chains the end of the PlaneFR pipeline (from the engine step onwards):
    3. engine             (matmat-ademe)
    4. extract_f_y_tot    (matmat-ademe)
    5. reformat_d_cba_monde_europe (matmat-ademe)
    6. reformat_d_cba_k   (matmat-ademe)
    7. export_dS
    8. compute_ds_x_dom

Each step is delegated to the dedicated script (run_engine_batch.ps1) or
launched directly for the Python scripts (steps 4 to 8). All the steps
run from matmat-ademe. The paths are computed relative to the location of this
script, so that it works whatever the current directory it is invoked from.

Steps 5 (addition of the France F_Y_tot) and 6 process all the scenarios of
Module_PlaneFR/data/<version>, whether directly under
data/<version>/<scenario> or nested by SSP
(data/<version>/<SSP>/<scenario>, e.g. no_SSP/S1_2050, SSP1_2050/TEND_2050).

Stops at the first failure (non-zero exit code) to avoid chaining steps on
incomplete data.

The Exiobase version is passed as a parameter (-Version, 3.11.2 by default):
it is forwarded to run_engine_batch.ps1 (which writes it into the settings
file) and to the Python scripts through the environment variable
PLANEFR_EXIOBASE_VERSION.
    Example: .\run_pipeline_from_engine.ps1 -Version 3.11.2
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

$env:PLANEFR_EXIOBASE_VERSION = $Version

$scriptsDir     = $PSScriptRoot
$matmatAdemeDir = Split-Path -Parent $scriptsDir

function Invoke-Stage {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host "`n########## $Name ##########" -ForegroundColor Green

    & $Action

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Pipeline interrupted: step '$Name' failed (code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Invoke-Stage "3. engine" {
    & (Join-Path $scriptsDir "run_engine_batch.ps1") -Version $Version
}

Invoke-Stage "4. extract_f_y_tot" {
    Set-Location $matmatAdemeDir
    uv run python (Join-Path $scriptsDir "extract_f_y_tot.py")
}

Invoke-Stage "5. reformat_d_cba_monde_europe" {
    Set-Location $matmatAdemeDir
    uv run python (Join-Path $scriptsDir "reformat_d_cba_monde_europe.py")
}

Invoke-Stage "6. reformat_d_cba_k" {
    Set-Location $matmatAdemeDir
    uv run python (Join-Path $scriptsDir "reformat_d_cba_k.py")
}

Invoke-Stage "7. export_dS" {
    Set-Location $matmatAdemeDir
    uv run python (Join-Path $scriptsDir "export_dS.py")
}

Invoke-Stage "8. compute_ds_x_dom" {
    Set-Location $matmatAdemeDir
    uv run python (Join-Path $scriptsDir "compute_ds_x_dom.py")
}

Write-Host "`nFull pipeline completed successfully (version $Version)." -ForegroundColor Green
