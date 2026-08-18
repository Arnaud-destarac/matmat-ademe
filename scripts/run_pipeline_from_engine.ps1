<#
Enchaine la fin du pipeline PlaneFR (a partir de l'etape engine) :
    3. engine             (matmat-ademe)
    4. extract_f_y_tot    (matmat-ademe)
    5. reformat_d_cba_monde_europe (matmat-ademe)
    6. reformat_d_cba_k   (matmat-ademe)

Chaque etape est deleguee au script dedie (run_engine_batch.ps1) ou lancee
directement pour les scripts Python (etapes 4 a 6). Toutes les etapes
tournent depuis matmat-ademe. Les chemins sont calcules relativement a
l'emplacement de ce script, pour fonctionner quel que soit le repertoire
courant depuis lequel il est invoque.

S'arrete au premier echec (code de sortie non nul) pour eviter d'enchainer
des etapes sur des donnees incompletes.
#>

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
        Write-Host "Pipeline interrompu : echec de l'etape '$Name' (code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Invoke-Stage "3. engine" {
    & (Join-Path $scriptsDir "run_engine_batch.ps1")
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

Write-Host "`nPipeline complet termine avec succes." -ForegroundColor Green
