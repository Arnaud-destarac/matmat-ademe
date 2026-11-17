<#
Chains the gmrio_to_snac_s step for each SSP scenario present in
data\4-PlaneFR\2-shocks\3-SSPs_2050, adapting the paths (scenario)
in gmrio_to_snac_S_SSPs.json before each run.

Assumes that the engine step has already been run for these scenarios
(see run_engine_batch_SSPs.ps1): path_in.accounts points to
.\4-PlaneFR\Outputs\World\<scenario>.

The outputs are written to
.\4-PlaneFR\Outputs_inter\gmrio_to_snac_s\SSPs\<scenario>, then their
F_x_dom are replaced by those of the reference output
(SSPs\$referenceScenarioName).

To be run from the matmat-ademe environment (pipeline carried in
src/matmat/workflows/pipelines/accounts/gmrio_to_snac_s).

-Suffix (e.g. "_agri"): reads the shocks in 3-SSPs_2050<Suffix>, the accounts
in Outputs\World\<scenario><Suffix> and writes to SSPs<Suffix>\<scenario><Suffix>.
The reference output (F_x_dom) is read in SSPs<Suffix>\<ReferenceScenarioName>:
if this scenario is one of the shocks (e.g. Base_year_agri), it is processed
first and its F_x_dom are not replaced.
#>

param(
    # Suffix of the shock and output folders ("" by default, e.g. "_agri")
    [string]$Suffix = "",
    # Reference gmrio_to_snac_s output whose F_x_dom are copied into each
    # scenario (the French domestic intensities are not shocked)
    [string]$ReferenceScenarioName = "Base_year_2015"
)

$projectDir = Split-Path -Parent $PSScriptRoot

$gmrioSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\2-gmrio_to_snac_s\gmrio_to_snac_S_SSPs.json"
$shocksDir         = Join-Path $projectDir "data\4-PlaneFR\2-shocks\3-SSPs_2050$Suffix"

function Add-Suffix {
    param([string]$Name)
    # Appends $Suffix to the name unless it already ends with it
    if ($Name.EndsWith($Suffix)) { return $Name }
    return "$Name$Suffix"
}

Set-Location $projectDir

# Decomposition of the initial paths:
# - accounts: "...\Outputs\World\<scenario>" -> parent folder
# - path_out: "...\SSPs<suffix>\<scenario>" -> parent folder, brought back to
#   "...\SSPs" (the JSON keeps the last path used, with or without suffix)
$initialSettings = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json
$accountsBaseDir = Split-Path -Parent $initialSettings.path_in.accounts
$gmrioOutBaseDir = [regex]::Replace((Split-Path -Parent $initialSettings.path_out), "_agri$", "") + $Suffix

# The paths of the settings are relative to the data folder
$dataDir = Join-Path $projectDir "data"

function Set-GmrioToSnacSSettings {
    param(
        # Name of the scenario sub-folder (e.g. "SSP2_2050")
        [string]$ScenarioName
    )

    $settings = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json

    $settings.path_in.accounts = Join-Path $accountsBaseDir (Add-Suffix $ScenarioName)
    $settings.path_out         = Join-Path $gmrioOutBaseDir (Add-Suffix $ScenarioName)

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($gmrioSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === gmrio_to_snac_s step: one run per scenario present in
# data\4-PlaneFR\2-shocks\3-SSPs_2050 ===

# Reference scenario first: its F_x_dom are used by the following ones
$scenarios = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name |
    Sort-Object { (Add-Suffix $_) -ne $ReferenceScenarioName }, { $_ }
$failed    = $false

foreach ($scenario in $scenarios) {
    Write-Host "=== $scenario : gmrio_to_snac_s ===" -ForegroundColor Cyan

    Set-GmrioToSnacSSettings -ScenarioName $scenario

    uv run python -m matmat.cli -p gmrio_to_snac_s -st $gmrioSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "gmrio_to_snac_s failed for $scenario (code $LASTEXITCODE)" -ForegroundColor Red
        $failed = $true
        continue
    }

    # === Replacement of the F_x_dom by those of the reference output ===
    if ((Add-Suffix $scenario) -eq $ReferenceScenarioName) {
        continue
    }
    $refDir   = Join-Path $dataDir (Join-Path $gmrioOutBaseDir $ReferenceScenarioName)
    $scenDir  = Join-Path $dataDir (Join-Path $gmrioOutBaseDir (Add-Suffix $scenario))
    $settings = Get-Content -Raw -Path $gmrioSettingsPath | ConvertFrom-Json

    Write-Host "--- $scenario : replacing the F_x_dom by those of $refDir ---" -ForegroundColor Cyan

    foreach ($ext in @($settings.extension_names)) {
        $src = Join-Path $refDir  "extensions\dom_$ext\F_x_dom.pkl"
        $dst = Join-Path $scenDir "extensions\dom_$ext\F_x_dom.pkl"
        if (-not (Test-Path $src)) {
            Write-Host "Reference F_x_dom not found: $src" -ForegroundColor Red
            $failed = $true
            continue
        }
        Copy-Item -Path $src -Destination $dst -Force
    }
}

if ($failed) {
    exit 1
}
