<#
Chains the SSP steps in order:
1. extract_S_SSPs              (extract_S_SSPs.py: 2050/2020 ratios of F, x, S
                                of the IMAGE scenarios -> sheets of
                                Matching_extensions_EXIOBASE_IMAGE.xlsx)
2. generate_shock_dS           (generate_shock_dS.py: dS_x_dom and dA in
                                2-shocks\3-SSPs_2050\<SSP>_2050)
3. engine                      (run_engine_batch_SSPs.ps1)
4. gmrio_to_snac_s             (run_gmrio_to_snac_s_batch_SSPs.ps1)
5. update_calib_fr             (run_update_calib_fr_batch_SSPs.ps1)
6. engine France               (run_engine_batch.ps1: baselines + shocks of
                                1-transitions_2050 on each set of accounts
                                of Outputs\France, outputs in
                                Module_PlaneFR/data/<version>/<SSP|no_SSP>/)
7. reformat_d_cba_monde_europe (reformat_d_cba_monde_europe.py)
8. reformat_d_cba_k            (reformat_d_cba_k.py)
9. export_dS                   (export_dS.py: S_extraction.xlsx)
10. compute_ds_x_dom           (compute_ds_x_dom.py: dS_x_dom of the manual
                                shocks + application of the F_Y_tot shocks)

No extract_f_y_tot step: it only depends on raw Exiobase (World F_Y_tot of
Base_year_2015/2019), not on the scenarios; it must have been run at least
once (run_pipeline_from_engine.ps1 or by hand) so that
reformat_d_cba_monde_europe finds Outputs\World\Base_year_*\...\F_Y_tot.pkl.

Steps 7 and 8 (as in run_pipeline_from_engine.ps1) process all the scenarios
of Module_PlaneFR/data/<version>, including those nested by SSP
(data/<version>/<SSP>/<scenario>). The version is passed to the Python
scripts through the environment variable PLANEFR_EXIOBASE_VERSION.

Stops if a step ends with an error code (among the .ps1 scripts, only
run_gmrio_to_snac_s_batch_SSPs.ps1 returns exit 1 on failure; the others
report their failures by scenario without interrupting the loop).
#>

param(
    # Exiobase version to use for update_calib_fr and the reformatting
    # scripts (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

$env:PLANEFR_EXIOBASE_VERSION = $Version

$matmatAdemeDir = Split-Path -Parent $PSScriptRoot

$steps = @(
    @{ Name = "extract_S_SSPs";              Script = "extract_S_SSPs.py" },
    @{ Name = "generate_shock_dS";           Script = "generate_shock_dS.py" },
    @{ Name = "engine";                    Script = "run_engine_batch_SSPs.ps1";          Args = @{} },
    @{ Name = "gmrio_to_snac_s";             Script = "run_gmrio_to_snac_s_batch_SSPs.ps1"; Args = @{} },
    @{ Name = "update_calib_fr";             Script = "run_update_calib_fr_batch_SSPs.ps1"; Args = @{ Version = $Version } },
    @{ Name = "engine France";               Script = "run_engine_batch.ps1";               Args = @{ Version = $Version } },
    @{ Name = "reformat_d_cba_monde_europe"; Script = "reformat_d_cba_monde_europe.py" },
    @{ Name = "reformat_d_cba_k";            Script = "reformat_d_cba_k.py" },
    @{ Name = "export_dS";                   Script = "export_dS.py" },
    @{ Name = "compute_ds_x_dom";            Script = "compute_ds_x_dom.py" }
)

foreach ($step in $steps) {
    Write-Host "########## Step $($step.Name) ##########" -ForegroundColor Magenta

    $scriptPath = Join-Path $PSScriptRoot $step.Script
    $global:LASTEXITCODE = 0
    if ($step.Script.EndsWith(".py")) {
        Set-Location $matmatAdemeDir
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
