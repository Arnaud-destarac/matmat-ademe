<#
Chains the SSP steps in order. Each step is named after the folder of
planeFR\scripts holding its script:
    b-ssp_shocks       extract_S_SSPs.py: 2050/2020 ratios of F, x, S of the IMAGE
                       scenarios -> sheets of Matching_extensions_EXIOBASE_IMAGE.xlsx
    b-ssp_shocks       generate_shock_dS.py: dS_x_dom and dA in 2-shocks\3-SSPs_2050\<SSP>_2050
    4-engine           run_engine_batch_SSPs.ps1: World engine, one run per SSP scenario
    2-gmrio_to_snac_s  run_gmrio_to_snac_s_batch_SSPs.ps1
    3-update_calib_fr  run_update_calib_fr_batch_SSPs.ps1
    4-engine           run_engine_batch.ps1: baselines + shocks of 1-transitions_2050
                       on each set of accounts of Outputs\France, outputs in
                       Module_PlaneFR/data/<version>/<SSP|no_SSP>/
    5-reformat         reformat_d_cba_monde_europe.py, reformat_d_cba_k.py
    a-manual_shocks    export_dS.py (S_extraction.xlsx), compute_ds_x_dom.py
                       (dS_x_dom of the manual shocks + F_Y_tot shocks)
    6-scenario_groups  build_scenario_groups.py (groups of Module_PlaneFR/data/scenario_groups.json)

No extract_f_y_tot step: it only depends on raw Exiobase (World F_Y_tot of
Base_year_2015/2019), not on the scenarios; it must have been run at least
once (run_full_pipeline.ps1, run_pipeline_from_engine.ps1 or by hand) so that
reformat_d_cba_monde_europe finds Outputs\World\Base_year_*\...\F_Y_tot.pkl.

The reformatting steps process all the scenarios of
Module_PlaneFR/data/<version>, including those nested by SSP
(data/<version>/<SSP>/<scenario>). The version is passed to the Python
scripts through the environment variable PLANEFR_EXIOBASE_VERSION.

Stops if a step ends with an error code. The batch .ps1 scripts process all
their scenarios even when one fails, then return exit code 1 if at least one
run failed.
#>

param(
    # Exiobase version to use for update_calib_fr and the reformatting
    # scripts (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

. (Join-Path $PSScriptRoot "..\_common\planefr_common.ps1")

$env:PLANEFR_EXIOBASE_VERSION = $Version

# Script paths relative to planeFR\scripts
$steps = @(
    @{ Name = "b-ssp_shocks: extract_S_SSPs";                Script = "shocks\b-ssp_shocks\extract_S_SSPs.py" },
    @{ Name = "b-ssp_shocks: generate_shock_dS";             Script = "shocks\b-ssp_shocks\generate_shock_dS.py" },
    @{ Name = "4-engine: run_engine_batch_SSPs (World)";     Script = "4-engine\run_engine_batch_SSPs.ps1";                   Args = @{} },
    @{ Name = "2-gmrio_to_snac_s: run_gmrio_to_snac_s_batch_SSPs"; Script = "2-gmrio_to_snac_s\run_gmrio_to_snac_s_batch_SSPs.ps1"; Args = @{} },
    @{ Name = "3-update_calib_fr: run_update_calib_fr_batch_SSPs"; Script = "3-update_calib_fr\run_update_calib_fr_batch_SSPs.ps1"; Args = @{ Version = $Version } },
    @{ Name = "4-engine: run_engine_batch (France)";         Script = "4-engine\run_engine_batch.ps1";                        Args = @{ Version = $Version } },
    @{ Name = "5-reformat: reformat_d_cba_monde_europe";     Script = "5-reformat\reformat_d_cba_monde_europe.py" },
    @{ Name = "5-reformat: reformat_d_cba_k";                Script = "5-reformat\reformat_d_cba_k.py" },
    @{ Name = "a-manual_shocks: export_dS";                  Script = "shocks\a-manual_shocks\export_dS.py" },
    @{ Name = "a-manual_shocks: compute_ds_x_dom";           Script = "shocks\a-manual_shocks\compute_ds_x_dom.py" },
    @{ Name = "6-scenario_groups: build_scenario_groups";    Script = "6-scenario_groups\build_scenario_groups.py" }
)

foreach ($step in $steps) {
    Write-Host "########## Step $($step.Name) ##########" -ForegroundColor Magenta

    $scriptPath = Join-Path $PlanefrScriptsDir $step.Script
    $global:LASTEXITCODE = 0
    if ($step.Script.EndsWith(".py")) {
        Set-Location $MatmatAdemeDir
        uv run python $scriptPath
    }
    else {
        $scriptArgs = $step.Args
        & $scriptPath @scriptArgs
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Stopped: step $($step.Name) failed (code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "########## All the SSP steps are done ##########" -ForegroundColor Green
