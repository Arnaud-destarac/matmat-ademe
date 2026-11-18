"""
Paths shared by the PlaneFR pipeline scripts.

No path is specific to a machine: everything is derived from the location of
this file, so that the repository works for anyone who clones it. Layout:

    <root>/
    ├── MatMat/matmat-ademe/
    │   ├── planeFR/
    │   │   ├── scripts/
    │   │   │   ├── planefr.py      pipeline command
    │   │   │   ├── _common/        this folder
    │   │   │   └── <chain>/        scripts of each chain (base_accounts, france_shocks, outputs...)
    │   │   └── parameters/         settings templates, bridge matrices, manual shocks (versioned)
    │   └── data/4-PlaneFR/         accounts, shocks, outputs (not versioned)
    └── Module_PlaneFR/

The pipeline command (planefr.py) takes them from here too, through
planefr_settings.Layout.default().

The scripts of the chain folders make this folder importable with:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_common"))

Environment variables (optional):
    PLANEFR_MODULE_DIR        Module_PlaneFR folder, if it is not at <root>/Module_PlaneFR
    PLANEFR_EXIOBASE_VERSION  Exiobase version of the data (3.11.2 by default; set
                              by planefr.py from --version)

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
# Sub-folders of Module_PlaneFR/data
MODULE_DATA_DIR = MODULE_PLANEFR_DIR / "data"
# Inputs of the shocks: Matching_EXIOBASE_IMAGE.xlsx, S_extraction.xlsx,
# input_data/ (IMAGE scenarios csv, Nutrients.xlsx)
MODULE_INPUT_SHOCKS_DIR = MODULE_DATA_DIR / "Input_Shocks_MatMat"
# Results of the engine (by Exiobase version) and scenario_groups.json
MODULE_OUTPUTS_DIR = MODULE_DATA_DIR / "Outputs_MatMat"
# bridge_matrices.xlsx, indicator_computing.xlsx
MODULE_POST_PROCESSING_DIR = MODULE_DATA_DIR / "Post_processing"
# Results of the France engine, by scenario: Module_PlaneFR/data/Outputs_MatMat/<version>
DATA_VERSION_DIR = MODULE_OUTPUTS_DIR / EXIOBASE_VERSION
# Raw engine outputs, split by year:
#   2019_raw/  2019_FR (France engine) and 2019_W, 2019_EU27, 2019_<code> (reformat_d_cba_monde_europe.py)
#   2050_raw/  <group>/<scenario> of the France engine (no_SSP, SSP2_2050, ..._agri)
# The display groups of scenario_groups.json (ADEME, CONF, S1+...) stay directly
# in DATA_VERSION_DIR.
RAW_2019_DIR = DATA_VERSION_DIR / "2019_raw"
RAW_2050_DIR = DATA_VERSION_DIR / "2050_raw"
RAW_DIR_NAMES = {RAW_2019_DIR.name, RAW_2050_DIR.name}


def find_all_scenario_dirs():
    """Every scenario folder (containing extensions/) of DATA_VERSION_DIR:
    2019_raw/<scenario>, 2050_raw/<group>/<scenario> and the display groups
    <group>/<scenario> (or <scenario>) directly in DATA_VERSION_DIR."""
    found = []
    for root in (RAW_2019_DIR, RAW_2050_DIR, DATA_VERSION_DIR):
        if not root.is_dir():
            continue
        for top in sorted(p for p in root.iterdir() if p.is_dir()):
            if root == DATA_VERSION_DIR and top.name in RAW_DIR_NAMES:
                continue
            if (top / "extensions").is_dir():
                found.append(top)
                continue
            found.extend(sub for sub in sorted(top.iterdir()) if (sub / "extensions").is_dir())
    return found

# planefr_lib (imported by some scripts)
PLANEFR_NOTEBOOKS_DIR = MODULE_PLANEFR_DIR / "notebooks"

# Settings template of the World engine of the SSP scenarios
# (engine_ssps step of planefr.py, which never changes its path_in.accounts)
SSP_ENGINE_SETTINGS_FILE = PARAMETERS_DIR / "4-engine" / "settings_engine_SSPs.json"


def get_ssp_base_accounts_dir():
    """World accounts to which the engine applies the SSP shocks: path_in.accounts
    of the template settings_engine_SSPs.json (relative to the data folder of
    matmat-ademe).

    Single source of the base year of the SSP shocks: generate_shock_dS.py and
    generate_shock_agri.py read the structure of the shocks there (S_x_dom, A,
    detail_levels, base_year), so that it is that of the accounts actually
    shocked by the engine_ssps step of planefr.py."""
    settings = json.loads(SSP_ENGINE_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    return MATMAT_DATA_DIR / settings["path_in"]["accounts"].replace("\\", "/")
