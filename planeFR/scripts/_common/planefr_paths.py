"""
Paths shared by the PlaneFR pipeline scripts.

No path is specific to a machine: everything is derived from the location of
this file, so that the repository works for anyone who clones it. Layout:

    <root>/
    ├── MatMat/matmat-ademe/
    │   ├── planeFR/
    │   │   ├── scripts/
    │   │   │   ├── _common/        this folder
    │   │   │   └── <step>/         scripts of each step (1-exiobase3_eeio, shocks/a-manual_shocks...)
    │   │   └── parameters/         settings templates, bridge matrices, manual shocks (versioned)
    │   └── data/4-PlaneFR/         accounts, shocks, outputs (not versioned)
    └── Module_PlaneFR/

The PowerShell scripts use the same layout (planefr_common.ps1).

The scripts of the step folders make this folder importable with:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_common"))

Environment variables (optional):
    PLANEFR_MODULE_DIR        Module_PlaneFR folder, if it is not at <root>/Module_PlaneFR
    PLANEFR_EXIOBASE_VERSION  Exiobase version of the data (3.11.2 by default; set
                              by the PowerShell pipeline scripts from -Version)

The data folder of matmat-ademe is <matmat-ademe>/data; the data_dir of
config.toml must point to the same folder.
"""

import json
import os
from pathlib import Path

COMMON_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = COMMON_DIR.parent
PLANEFR_DIR = SCRIPTS_DIR.parent
MATMAT_DIR = PLANEFR_DIR.parent

# Versioned parameters: settings templates, bridge matrices, manual shocks
PARAMETERS_DIR = PLANEFR_DIR / "parameters"

MATMAT_DATA_DIR = MATMAT_DIR / "data"
PLANEFR_DATA_DIR = MATMAT_DATA_DIR / "4-PlaneFR"

MODULE_PLANEFR_DIR = Path(
    os.environ.get("PLANEFR_MODULE_DIR", MATMAT_DIR.parents[1] / "Module_PlaneFR")
).resolve()
if not MODULE_PLANEFR_DIR.is_dir():
    raise FileNotFoundError(
        f"Module_PlaneFR folder not found: {MODULE_PLANEFR_DIR}. "
        f"Set the PLANEFR_MODULE_DIR environment variable to its location."
    )

EXIOBASE_VERSION = os.environ.get("PLANEFR_EXIOBASE_VERSION", "3.11.2")
# Results of the France engine, by scenario: Module_PlaneFR/data/<version>
DATA_VERSION_DIR = MODULE_PLANEFR_DIR / "data" / EXIOBASE_VERSION
# planefr_lib (imported by some scripts)
PLANEFR_NOTEBOOKS_DIR = MODULE_PLANEFR_DIR / "notebooks"

# Settings template of the World engine of the SSP scenarios
# (4-engine/run_engine_batch_SSPs.ps1, which never changes its path_in.accounts)
SSP_ENGINE_SETTINGS_FILE = PARAMETERS_DIR / "4-engine" / "settings_engine_SSPs.json"


def get_ssp_base_accounts_dir():
    """World accounts to which the engine applies the SSP shocks: path_in.accounts
    of the template settings_engine_SSPs.json (relative to the data folder of
    matmat-ademe).

    Single source of the base year of the SSP shocks: generate_shock_dS.py and
    generate_shock_agri.py read the structure of the shocks there (S_x_dom, A,
    detail_levels, base_year), so that it is that of the accounts actually
    shocked by run_engine_batch_SSPs.ps1."""
    settings = json.loads(SSP_ENGINE_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    return MATMAT_DATA_DIR / settings["path_in"]["accounts"].replace("\\", "/")
