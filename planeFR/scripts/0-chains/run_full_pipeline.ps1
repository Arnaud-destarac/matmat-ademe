<#
Chains the whole PlaneFR pipeline. Each stage is named after the folder of
planeFR\scripts holding its script:
    1-exiobase3_eeio   run_exiobase3_eeio_batch.ps1  (adapter + World engine, 2015 and 2019)
    2-gmrio_to_snac_s  run_gmrio_to_snac_s_batch.ps1 (France SNAC accounts, shock extension folders)
    3-update_calib_fr  run_update_calib_fr_batch.ps1 (datapack environment)
    4-engine           run_engine_batch.ps1          (France engine)
    1-exiobase3_eeio   extract_f_y_tot.py            (direct pressures of the final demand)
    5-reformat         reformat_d_cba_monde_europe.py, reformat_d_cba_k.py
    a-manual_shocks    export_dS.py, compute_ds_x_dom.py
    second pass        run_pipeline_from_engine.ps1 (4-engine to 6-scenario_groups)
                       or, with -SinglePass, 6-scenario_groups build_scenario_groups.py alone

update_calib_fr is the only step that must run from the environment of the
datapack project (sibling of matmat-ademe); all the others run from
matmat-ademe. The paths are computed relative to the location of this script,
so that it works whatever the current directory it is invoked from.

Second pass: compute_ds_x_dom.py computes the dS_x_dom of the manual shocks
from the 2050 production output by the engine, which the engine must then
apply. The first pass applies the dS_x_dom of the previous run (kept by
rebuild_shock_extensions.py), exact if neither my_manual_param.xlsx nor the
accounts or system shocks have changed; the second pass guarantees exactness
in all cases (production does not depend on the dS_x_dom, a single iteration
is enough). -SinglePass skips it (faster, to be reserved for the case above).

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

. (Join-Path $PSScriptRoot "..\_common\planefr_common.ps1")

$env:PLANEFR_EXIOBASE_VERSION = $Version

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

function Invoke-PythonScript {
    param(
        # Path of the script relative to planeFR\scripts (e.g. "5-reformat\reformat_d_cba_k.py")
        [string]$RelativePath
    )
    Set-Location $MatmatAdemeDir
    uv run python (Join-Path $PlanefrScriptsDir $RelativePath)
}

Invoke-Stage "1-exiobase3_eeio: run_exiobase3_eeio_batch" {
    & (Join-Path $PlanefrScriptsDir "1-exiobase3_eeio\run_exiobase3_eeio_batch.ps1") -Version $Version
}

Invoke-Stage "2-gmrio_to_snac_s: run_gmrio_to_snac_s_batch" {
    & (Join-Path $PlanefrScriptsDir "2-gmrio_to_snac_s\run_gmrio_to_snac_s_batch.ps1") -Version $Version
}

Invoke-Stage "3-update_calib_fr: run_update_calib_fr_batch" {
    & (Join-Path $PlanefrScriptsDir "3-update_calib_fr\run_update_calib_fr_batch.ps1") -Version $Version
}

Invoke-Stage "4-engine: run_engine_batch" {
    & (Join-Path $PlanefrScriptsDir "4-engine\run_engine_batch.ps1") -Version $Version
}

Invoke-Stage "1-exiobase3_eeio: extract_f_y_tot" {
    Invoke-PythonScript "1-exiobase3_eeio\extract_f_y_tot.py"
}

Invoke-Stage "5-reformat: reformat_d_cba_monde_europe" {
    Invoke-PythonScript "5-reformat\reformat_d_cba_monde_europe.py"
}

Invoke-Stage "5-reformat: reformat_d_cba_k" {
    Invoke-PythonScript "5-reformat\reformat_d_cba_k.py"
}

Invoke-Stage "a-manual_shocks: export_dS" {
    Invoke-PythonScript "shocks\a-manual_shocks\export_dS.py"
}

Invoke-Stage "a-manual_shocks: compute_ds_x_dom" {
    Invoke-PythonScript "shocks\a-manual_shocks\compute_ds_x_dom.py"
}

if (-not $SinglePass) {
    # The second pass ends with build_scenario_groups
    Invoke-Stage "second pass (engine with up-to-date dS_x_dom)" {
        & (Join-Path $PlanefrScriptsDir "0-chains\run_pipeline_from_engine.ps1") -Version $Version
    }
}
else {
    Invoke-Stage "6-scenario_groups: build_scenario_groups" {
        Invoke-PythonScript "6-scenario_groups\build_scenario_groups.py"
    }
}

Write-Host "`nFull pipeline completed successfully (version $Version)." -ForegroundColor Green
