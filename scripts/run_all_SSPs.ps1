<#
Enchaine les trois etapes SSPs dans l'ordre :
1. engine          (run_engine_batch_SSPs.ps1)
2. gmrio_to_snac_s (run_gmrio_to_snac_s_batch_SSPs.ps1)
3. update_calib_fr (run_update_calib_fr_batch_SSPs.ps1)

S'arrete si une etape se termine avec un code d'erreur (seul
run_gmrio_to_snac_s_batch_SSPs.ps1 renvoie exit 1 en cas d'echec ; les deux
autres signalent leurs echecs par scenario sans interrompre la boucle).
#>

param(
    # Version Exiobase a utiliser par update_calib_fr (ex. "3.11.2")
    [string]$Version = "3.11.2"
)

$steps = @(
    @{ Name = "engine";          Script = "run_engine_batch_SSPs.ps1";          Args = @{} },
    @{ Name = "gmrio_to_snac_s"; Script = "run_gmrio_to_snac_s_batch_SSPs.ps1"; Args = @{} },
    @{ Name = "update_calib_fr"; Script = "run_update_calib_fr_batch_SSPs.ps1"; Args = @{ Version = $Version } }
)

foreach ($step in $steps) {
    Write-Host "########## Etape $($step.Name) ##########" -ForegroundColor Magenta

    $scriptArgs = $step.Args
    $global:LASTEXITCODE = 0
    & (Join-Path $PSScriptRoot $step.Script) @scriptArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Arret : echec de l'etape $($step.Name) (code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "########## Toutes les etapes SSPs sont terminees ##########" -ForegroundColor Green
