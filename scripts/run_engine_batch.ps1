<#
Chains the engine step (baseline + one run per accounts/scenario pair) by
adapting the paths in the JSON settings file before each run.

Assumes that the gmrio_to_snac_s and update_calib_fr steps have already been
run beforehand (see run_calib_fr_batch.ps1 / run_update_calib_fr_batch.ps1
/ run_update_calib_fr_batch_SSPs.ps1) and that their outputs are available.

The scenario runs iterate over each accounts folder present in
data\4-PlaneFR\Outputs\France (except folders containing "2019") and over each
scenario of data\4-PlaneFR\2-shocks\1-transitions_2050. The outputs are
written to Module_PlaneFR\data\<Version>\<group>\<scenario> (-Version,
3.11.2 by default), with <group> = "no_SSP" for the Base_year_2015 accounts,
and the name of the accounts folder otherwise (e.g. "SSP2_2050").
The Base_year_2015 baseline is written to Module_PlaneFR\data\<Version>\no_SSP,
then copied into each other group (SSP1_2050...) to serve as the reference
scenario there; the 2019 baseline stays in Module_PlaneFR\data\<Version>\2019_FR.

-Suffix (e.g. "_agri"): reads the shocks in 1-transitions_2050<Suffix> and the
accounts in Outputs\France<Suffix>, and ensures that every group and scenario
folder written ends with <Suffix>. The Base_year<Suffix> accounts then play
the role of Base_year_2015 (group no_SSP<Suffix>), and the reference baseline
is the Base_year<Suffix> scenario of these accounts
(no_SSP<Suffix>\Base_year<Suffix>), copied into each other group. The
2015/2019 baselines without shock are not recomputed.
#>

param(
    # Exiobase version to use (e.g. "3.11.2")
    [string]$Version = "3.11.2",
    # Suffix of the shock, accounts and output folders ("" by default, e.g. "_agri")
    [string]$Suffix = ""
)

$projectDir = Split-Path -Parent $PSScriptRoot

$engineSettingsPath = Join-Path $projectDir "data\4-PlaneFR\Settings\4-engine\settings_engine_France_shocks.json"
$shocksDir          = Join-Path $projectDir "data\4-PlaneFR\2-shocks\1-transitions_2050$Suffix"

function Add-Suffix {
    param([string]$Name)
    # Appends $Suffix to the name unless it already ends with it
    if ($Name.EndsWith($Suffix)) { return $Name }
    return "$Name$Suffix"
}

Set-Location $projectDir

# Base output folder (e.g. "...\Module_PlaneFR\data\3.11.2"): data folder of the
# initial path_out ("...\data\<version>\<scenario>"), followed by the
# requested version.
$initialSettings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json
# The initial path_out can be "...\data\<version>\<scenario>" or, after a
# scenario run, "...\data\<version>\<group>\<scenario>": we therefore cut at the
# version folder rather than going up a fixed number of levels.
$engineOutDataDir = [regex]::Replace($initialSettings.path_out, "\\\d+\.\d+\.\d+(\\.*)?$", "")
$engineOutBaseDir = Join-Path $engineOutDataDir $Version

# Folder containing the France accounts (e.g. ".\4-PlaneFR\Outputs\France"):
# set here rather than deduced from the JSON, whose path_in.accounts changes at each run
$accountsBaseDir = ".\4-PlaneFR\Outputs\France$Suffix"

# Accounts folder whose scenario outputs go to "no_SSP<Suffix>"
$noSspAccountsName = if ($Suffix) { "Base_year$Suffix" } else { "Base_year_2015" }

# Baseline output copied into each group folder (no_SSP, SSP1_2050...), to
# serve as the reference scenario of the Module_PlaneFR figures. With
# -Suffix, it is the Base_year<Suffix> shock scenario of the
# $noSspAccountsName accounts (no baseline run without shock).
$referenceBaselineName = if ($Suffix) { "Base_year$Suffix" } else { "Base_year_2015" }

function Get-ScenarioGroup {
    param(
        # Name of the accounts folder (e.g. "Base_year_2015" or "SSP2_2050")
        [string]$AccountsName
    )
    if ($AccountsName -eq $noSspAccountsName) {
        return "no_SSP$Suffix"
    }
    return Add-Suffix $AccountsName
}

function Set-EngineSettings {
    param(
        # $null for a baseline run (no shock), otherwise name of the scenario
        # sub-folder (e.g. "S1_2050"). No [string] type here: PowerShell
        # would silently convert a $null passed as argument into "",
        # which would break the $null -eq $ScenarioName test below.
        $ScenarioName,
        # Base year of the accounts (only used for baseline runs).
        [int]$Year = 2015,
        # Name of the accounts folder in $accountsBaseDir (only used for
        # scenario runs, e.g. "Base_year_2015" or "SSP2_2050").
        [string]$AccountsName = $noSspAccountsName
    )

    $settings = Get-Content -Raw -Path $engineSettingsPath | ConvertFrom-Json

    $outBaseDir = $engineOutBaseDir

    if ($null -eq $ScenarioName) {
        $settings.path_in.accounts = Join-Path $accountsBaseDir "Base_year_$Year"
        $settings.path_in.shock    = $null
        if ($Year -eq 2019) {
            $settings.path_out = Join-Path $outBaseDir "2019_FR"
        }
        elseif ("Base_year_$Year" -eq $referenceBaselineName) {
            # Reference baseline: written to the no_SSP group, then copied
            # into the other groups (see end of the scenario loop)
            $settings.path_out = Join-Path (Join-Path $outBaseDir (Get-ScenarioGroup -AccountsName $noSspAccountsName)) "Base_year_$Year"
        }
        else {
            $settings.path_out = Join-Path $outBaseDir "Base_year_$Year"
        }
    }
    else {
        $group = Get-ScenarioGroup -AccountsName $AccountsName
        $settings.path_in.accounts = Join-Path $accountsBaseDir $AccountsName
        $settings.path_in.shock    = ".\4-PlaneFR\2-shocks\1-transitions_2050$Suffix\$ScenarioName"
        $settings.path_out         = Join-Path (Join-Path $outBaseDir $group) (Add-Suffix $ScenarioName)
    }

    $json = $settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($engineSettingsPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# === Engine step: 2015 baseline, 2019 baseline, then one run per pair
# (accounts folder of data\4-PlaneFR\Outputs\France except "2019",
# scenario of data\4-PlaneFR\2-shocks\1-transitions_2050) ===

$baselineYears = if ($Suffix) { @() } else { 2015, 2019 }
$scenarios    = Get-ChildItem -Path $shocksDir -Directory | Select-Object -ExpandProperty Name
# no_SSP accounts first: their reference baseline is copied into the
# following groups
$accountsNames = Get-ChildItem -Path (Join-Path $projectDir "data\$accountsBaseDir") -Directory |
    Where-Object { $_.Name -notmatch "2019" } |
    Select-Object -ExpandProperty Name |
    Sort-Object { $_ -ne $noSspAccountsName }, { $_ }

foreach ($year in $baselineYears) {
    Write-Host "=== engine : baseline Base_year_$year ===" -ForegroundColor Cyan

    Set-EngineSettings -ScenarioName $null -Year $year

    uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Engine failed for baseline Base_year_$year (code $LASTEXITCODE)" -ForegroundColor Red
    }
}

foreach ($accountsName in $accountsNames) {
    foreach ($scenario in $scenarios) {
        # The reference baseline of this group is copied from no_SSP<Suffix>
        # (see below): no need to compute it
        if ($scenario -eq $referenceBaselineName -and $accountsName -ne $noSspAccountsName) {
            continue
        }

        Write-Host "=== engine : $accountsName / $scenario ===" -ForegroundColor Cyan

        Set-EngineSettings -ScenarioName $scenario -AccountsName $accountsName

        uv run python -m matmat.cli -e eeio -st $engineSettingsPath --no_confirm

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Engine failed for $accountsName / $scenario (code $LASTEXITCODE)" -ForegroundColor Red
        }
    }

    # === Copy of the reference baseline (written to no_SSP) into the group
    # folder ===
    $group = Get-ScenarioGroup -AccountsName $accountsName
    if ($accountsName -eq $noSspAccountsName) {
        continue
    }
    $baseline  = Join-Path (Join-Path $engineOutBaseDir (Get-ScenarioGroup -AccountsName $noSspAccountsName)) $referenceBaselineName
    $groupCopy = Join-Path (Join-Path $engineOutBaseDir $group) $referenceBaselineName

    if (-not (Test-Path (Join-Path $baseline "extensions"))) {
        Write-Host "Cannot copy $referenceBaselineName into $group : $baseline not found or incomplete" -ForegroundColor Red
        continue
    }
    Write-Host "--- $group : copy of $baseline ---" -ForegroundColor Cyan
    if (Test-Path $groupCopy) {
        Remove-Item -Path $groupCopy -Recurse -Force
    }
    Copy-Item -Path $baseline -Destination $groupCopy -Recurse
}
