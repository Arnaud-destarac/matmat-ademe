<#
"_agri" variant of run_all_SSPs.ps1: chains the same steps on the agricultural
shocks of 2-shocks\1-transitions_2050_agri and 2-shocks\3-SSPs_2050_agri.
Every folder generated takes the "_agri" suffix:
1. generate_shock_agri         (generate_shock_agri.py: regenerates
                                1-transitions_2050_agri and 3-SSPs_2050_agri from
                                1-transitions_2050 and 3-SSPs_2050,
                                plus a Base_year_agri scenario in each)
2. engine                      (run_engine_batch_SSPs.ps1 -Suffix _agri:
                                shocks of 3-SSPs_2050_agri, outputs in
                                Outputs\World\<scenario>_agri)
3. gmrio_to_snac_s             (run_gmrio_to_snac_s_batch_SSPs.ps1 -Suffix _agri:
                                outputs in Outputs_inter\gmrio_to_snac_s\SSPs_agri;
                                reference F_x_dom read in SSPs_agri\Base_year_agri)
4. update_calib_fr             (run_update_calib_fr_batch_SSPs.ps1 -Suffix _agri:
                                outputs in Outputs\France_agri)
5. engine France               (run_engine_batch.ps1 -Suffix _agri: shocks of
                                1-transitions_2050_agri on each set of accounts
                                of Outputs\France_agri, outputs in
                                Module_PlaneFR/data/<version>/<group>_agri/;
                                Base_year_agri accounts -> group no_SSP_agri,
                                whose Base_year_agri output is copied into
                                each other group as the reference)
6. reformat_d_cba_monde_europe (reformat_d_cba_monde_europe.py)
7. reformat_d_cba_k            (reformat_d_cba_k.py)
8. compute_ds_x_dom            (compute_ds_x_dom.py --only-f-y-tot: step 6
                                resets F_Y_tot to its base-year value in ALL the
                                scenario folders, "_agri" or not; the F_Y_tot
                                shocks are therefore reapplied there. The
                                dS_x_dom are not recomputed.)

generate_shock_agri.py reads the non-agricultural shocks 1-transitions_2050 and
3-SSPs_2050: run_all_SSPs.ps1 (which generates 3-SSPs_2050) must have been
run before if these shocks have changed.

Stops if a step ends with an error code (see run_all_SSPs.ps1).
#>

param(
    # Exiobase version to use for update_calib_fr and the reformatting
    # scripts (e.g. "3.11.2")
    [string]$Version = "3.11.2"
)

$env:PLANEFR_EXIOBASE_VERSION = $Version

$suffix = "_agri"

# "Base year" scenario created by generate_shock_agri.py (BASE_YEAR_SCENARIO)
$baseYearScenario = "Base_year$suffix"

$matmatAdemeDir = Split-Path -Parent $PSScriptRoot

$steps = @(
    @{ Name = "generate_shock_agri";         Script = "generate_shock_agri.py" },
    @{ Name = "engine";                      Script = "run_engine_batch_SSPs.ps1";          Args = @{ Suffix = $suffix } },
    @{ Name = "gmrio_to_snac_s";             Script = "run_gmrio_to_snac_s_batch_SSPs.ps1"; Args = @{ Suffix = $suffix; ReferenceScenarioName = $baseYearScenario } },
    @{ Name = "update_calib_fr";             Script = "run_update_calib_fr_batch_SSPs.ps1"; Args = @{ Version = $Version; Suffix = $suffix } },
    @{ Name = "engine France";               Script = "run_engine_batch.ps1";               Args = @{ Version = $Version; Suffix = $suffix } },
    @{ Name = "reformat_d_cba_monde_europe"; Script = "reformat_d_cba_monde_europe.py" },
    @{ Name = "reformat_d_cba_k";            Script = "reformat_d_cba_k.py" },
    @{ Name = "compute_ds_x_dom (F_Y_tot)";  Script = "compute_ds_x_dom.py";               PyArgs = @("--only-f-y-tot") }
)

foreach ($step in $steps) {
    Write-Host "########## Step $($step.Name) ($suffix) ##########" -ForegroundColor Magenta

    $scriptPath = Join-Path $PSScriptRoot $step.Script
    $global:LASTEXITCODE = 0
    if ($step.Script.EndsWith(".py")) {
        Set-Location $matmatAdemeDir
        # Arguments of the Python script (none by default)
        $pyArgs = if ($step.PyArgs) { $step.PyArgs } else { @() }
        uv run python $scriptPath @pyArgs
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

Write-Host "########## All the SSP steps ($suffix) are done ##########" -ForegroundColor Green
