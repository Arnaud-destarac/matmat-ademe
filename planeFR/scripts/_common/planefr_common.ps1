<#
Common paths and helpers of the PlaneFR PowerShell scripts, dot-sourced by
each of them (scripts of a step folder, e.g. planeFR\scripts\4-engine):
    . (Join-Path $PSScriptRoot "..\_common\planefr_common.ps1")

Layout (same as _common\planefr_paths.py for the Python scripts):
    matmat-ademe\
    |-- planeFR\
    |   |-- scripts\
    |   |   |-- _common\   this file
    |   |   `-- <step>\    scripts of each step (0-chains, 1-exiobase3_eeio...)
    |   `-- parameters\    settings templates, bridge matrices, manual shocks (versioned)
    `-- data\4-PlaneFR\    accounts, shocks, outputs (not versioned)
        `-- Settings_run\  settings files generated for each run (not versioned)

$PlanefrScriptsDir (planeFR\scripts) lets a script call the script of another
step, e.g. Join-Path $PlanefrScriptsDir "4-engine\run_engine_batch.ps1".

The JSON files of planeFR\parameters are TEMPLATES: the scripts never modify
them. Each run reads a template (Read-SettingsTemplate), changes the paths of
that run, then writes the result under data\4-PlaneFR\Settings_run
(Write-RunSettings), which is the file passed to matmat.cli. In the templates,
"{parameters}" stands for the planeFR\parameters folder; it is replaced by its
absolute path in the generated file (MatMat resolves the other relative paths
against the data_dir of config.toml, i.e. matmat-ademe\data).
#>

# $PSScriptRoot is the folder of this file (planeFR\scripts\_common), even
# when it is dot-sourced from another script
$PlanefrScriptsDir     = Split-Path -Parent $PSScriptRoot
$PlanefrDir           = Split-Path -Parent $PlanefrScriptsDir
$MatmatAdemeDir        = Split-Path -Parent $PlanefrDir
$PlanefrParametersDir  = Join-Path $PlanefrDir "parameters"
$PlanefrDataDir        = Join-Path $MatmatAdemeDir "data\4-PlaneFR"
$PlanefrRunSettingsDir = Join-Path $PlanefrDataDir "Settings_run"

# Token of the templates replaced by the absolute path of planeFR\parameters
$ParametersToken = "{parameters}"

function Read-SettingsTemplate {
    param(
        # Path of the template relative to planeFR\parameters
        # (e.g. "4-engine\settings_engine_SSPs.json")
        [string]$RelativePath
    )
    $templatePath = Join-Path $PlanefrParametersDir $RelativePath
    return Get-Content -Raw -Path $templatePath | ConvertFrom-Json
}

function Expand-ParametersToken {
    param($Value)
    # Replaces "{parameters}" by the absolute path of planeFR\parameters in a
    # string, or recursively in the properties of an object (e.g. path_in)
    if ($Value -is [string]) {
        return $Value.Replace($ParametersToken, $PlanefrParametersDir)
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        foreach ($property in $Value.PSObject.Properties) {
            $property.Value = Expand-ParametersToken $property.Value
        }
    }
    return $Value
}

function Write-RunSettings {
    param(
        # Path relative to planeFR\parameters of the template it comes from:
        # the generated file gets the same relative path under Settings_run
        [string]$RelativePath,
        $Settings
    )
    $Settings.path_in = Expand-ParametersToken $Settings.path_in
    $runPath = Join-Path $PlanefrRunSettingsDir $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runPath) | Out-Null
    $json = $Settings | ConvertTo-Json -Depth 10
    # Written as UTF-8 without BOM to avoid JSON parsing errors on the Python side
    [System.IO.File]::WriteAllText($runPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    return $runPath
}
