<#
Chains the whole PlaneFR pipeline:
    0. exiobase3_eeio_batch (matmat-ademe)
    1. gmrio_to_snac_s   (matmat-ademe)
    2. update_calib_fr   (datapack)
    3. engine             (matmat-ademe)
    4. extract_f_y_tot    (matmat-ademe)
    5. reformat_d_cba_monde_europe (matmat-ademe)
    6. reformat_d_cba_k   (matmat-ademe)
    7. export_dS
    8. compute_ds_x_dom
    9. second pass (run_pipeline_from_engine.ps1)

Each step is delegated to the dedicated script (run_gmrio_to_snac_s_batch.ps1,
run_update_calib_fr_batch.ps1, run_engine_batch.ps1) or launched directly
for the Python scripts (steps 4 to 8). update_calib_fr is the only step
that must run from the environment of the datapack project (sibling of
matmat-ademe); all the others run from matmat-ademe. The paths
are computed relative to the location of this script, so that it works
whatever the current directory it is invoked from.

Second pass (steps 3 to 8, via run_pipeline_from_engine.ps1): step 8
computes the dS_x_dom of the manual shocks from the 2050 production output
by step 3, which the engine must then apply. The first pass applies the
dS_x_dom of the previous run (kept by rebuild_shock_extensions.py), exact if
neither my_manual_param.xlsx nor the accounts or system shocks have changed;
the second pass guarantees exactness in all cases (production does not depend
on the dS_x_dom, a single iteration is enough). -SinglePass skips it (faster,
to be reserved for the case above).

Stops at the first failure (non-zero exit code) to avoid chaining steps on
incomplete data.

The Exiobase version is passed as a parameter (-Version, 3.11.2 by default):
it is forwarded to the .ps1 scripts of each step (which write it into the
settings files) and to the Python scripts through the environment variable
PLANEFR_EXIOBASE_VERSION.
    Example: .\run_full_pipeline.ps1 -Version 3.11.2
             .\run_full_pipeline.ps1 -Version 3.11.2 -SinglePass
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2",
    # Does not run the second pass (engine + post-processing)
    [switch]$SinglePass
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

Invoke-Stage "0. exiobase3_eeio_batch" {
    & (Join-Path $scriptsDir "run_exiobase3_eeio_batch.ps1") -Version $Version
}

Invoke-Stage "1. gmrio_to_snac_s" {
    & (Join-Path $scriptsDir "run_gmrio_to_snac_s_batch.ps1") -Version $Version
}

Invoke-Stage "2. update_calib_fr" {
    & (Join-Path $scriptsDir "run_update_calib_fr_batch.ps1") -Version $Version
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

if (-not $SinglePass) {
    Invoke-Stage "9. second pass (engine with up-to-date dS_x_dom)" {
        & (Join-Path $scriptsDir "run_pipeline_from_engine.ps1") -Version $Version
    }
}

Write-Host "`nFull pipeline completed successfully (version $Version)." -ForegroundColor Green
