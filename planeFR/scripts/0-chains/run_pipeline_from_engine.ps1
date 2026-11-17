<#
Chains the end of the PlaneFR pipeline, from the France engine onwards. Each
stage is named after the folder of planeFR\scripts holding its script:
    4-engine           run_engine_batch.ps1
    1-exiobase3_eeio   extract_f_y_tot.py
    5-reformat         reformat_d_cba_monde_europe.py, reformat_d_cba_k.py
    a-manual_shocks    export_dS.py, compute_ds_x_dom.py
    6-scenario_groups  build_scenario_groups.py (groups of Module_PlaneFR/data/scenario_groups.json)

All the steps run from matmat-ademe. The paths are computed relative to the
location of this script, so that it works whatever the current directory it
is invoked from.

The reformatting steps (addition of the France F_Y_tot, harmonization of the
GHG and raw-material extensions) process all the scenarios of
Module_PlaneFR/data/<version>, whether directly under data/<version>/<scenario>
or nested by group (data/<version>/<group>/<scenario>, e.g. no_SSP/S1_2050,
SSP2_2050/TEND_2050).

Stops at the first failure (non-zero exit code) to avoid chaining steps on
incomplete data.

The Exiobase version is passed as a parameter (-Version, 3.11.2 by default):
it is forwarded to run_engine_batch.ps1 and to the Python scripts through the
environment variable PLANEFR_EXIOBASE_VERSION.
    Example: .\run_pipeline_from_engine.ps1 -Version 3.11.2
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2"
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

Invoke-Stage "6-scenario_groups: build_scenario_groups" {
    Invoke-PythonScript "6-scenario_groups\build_scenario_groups.py"
}

Write-Host "`nPipeline completed successfully (version $Version)." -ForegroundColor Green
