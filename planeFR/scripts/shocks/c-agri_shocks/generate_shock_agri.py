"""
Generates, for each shock set of data/4-PlaneFR/2-shocks (1-transitions_2050,
3-SSPs_2050), an '_agri' variant (1-transitions_2050_agri, 3-SSPs_2050_agri)
in which only the stressors of the 'Food' sectors remain:

    - (region, ..., sector) columns of the Food sectors: dS = dS of the scenario
      (0 if the scenario does not shock the extension);
    - all the other columns: dS = -1, i.e. S_2050 = S_base x (1 + dS) = 0.

Exceptions for the S_Z extensions (see S_Z_FILTERS): dom_ghg_combustion keeps
the Food + fertilizer columns, dom_raw_materials keeps the Food rows (extracted
products) rather than the columns. The GHG extensions in S_x_dom
(dom_ghg_emissions, ghg_emissions) also keep the fertilizer columns (see
S_X_DOM_EXTRA_SECTORS).

The Food sectors are the 'sector' values with a 1 in the 'Food' column of the
'M' sheet of Module_PlaneFR/data/bridge_matrices.xlsx, plus FOOD_EXTRA_SECTORS
and minus FOOD_EXCLUDED_SECTORS.

Each <scenario> is first copied as is, without the data .xlsx files (system/:
dA, dY, dY_k as .pkl, detail_levels, info; extensions/: detail_levels, info),
then the dS (.pkl only) of all the extensions are rewritten. The extensions
processed are all those of the base accounts (EXTENSIONS_BASE_DIRS) having an
S_x_dom.pkl (dS_x_dom shock) or, failing that, an S_Z.pkl (dS_Z shock, columns
= user sectors; S_Y is not shocked); those missing from the original shock
folder are created (detail_levels.xlsx copied from the base accounts,
info.json).

An additional 'Base_year_agri' scenario is created in each '_agri' folder: no
shock on the system (system/ only contains detail_levels.xlsx and info.json),
dS = 0 on the Food sectors (S unchanged) and -1 elsewhere.
"""

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

# Shared modules of planeFR/scripts/_common
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
from planefr_paths import MATMAT_DIR, MODULE_PLANEFR_DIR, get_ssp_base_accounts_dir  # noqa: E402
from planefr_utils import make_pickle_portable  # noqa: E402

SHOCKS_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "2-shocks"
OUTPUTS_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "Outputs"
BRIDGE_FILE = MODULE_PLANEFR_DIR / "data" / "bridge_matrices.xlsx"

AGRI_SUFFIX = "_agri"
BASE_YEAR_SCENARIO = "Base_year_agri"

# Shock set -> extensions folder of the matching base accounts. For the SSP
# shocks, these are the World accounts to which the engine applies them
# (path_in.accounts of settings_engine_SSPs.json), as in generate_shock_dS.py.
EXTENSIONS_BASE_DIRS = {
    "1-transitions_2050": OUTPUTS_DIR / "France" / "Base_year_2015" / "extensions",
    "3-SSPs_2050": get_ssp_base_accounts_dir() / "extensions",
}

# Shocked extension coefficients, in order of preference
S_NAMES = ("S_x_dom", "S_Z")

FOOD_EXTRA_SECTORS = {"Products of forestry, logging and related services (02)"}
FOOD_EXCLUDED_SECTORS = {"Hotel and restaurant services (55)"}
FERTILIZER_SECTORS = {"N-fertiliser", "P- and other fertiliser"}

# S_Z extensions (rows = products, columns = user sectors): filtered axis and
# additional sectors kept. By default (S_x_dom), the columns of the Food
# sectors are kept.
#   - ghg_combustion: Food + fertilizer columns -> combustion emissions of the
#     sectors of the agri-food system;
#   - raw_materials: Food rows -> all the extracted biomass (agricultural and
#     forest), whatever the sector using it.
S_Z_FILTERS = {
    "dom_ghg_combustion": ("columns", FERTILIZER_SECTORS),
    "dom_raw_materials": ("index", set()),
}

# S_x_dom extensions for which the fertilizers are kept in addition to the
# Food sectors (GHG emissions attributable to the agri-food system).
S_X_DOM_EXTRA_SECTORS = {
    "dom_ghg_emissions": FERTILIZER_SECTORS,
    "ghg_emissions": FERTILIZER_SECTORS,
}


def load_food_sectors():
    bridge = pd.read_excel(BRIDGE_FILE, sheet_name="M")
    food = set(bridge.loc[bridge["Food"] == 1, "sector"])
    return (food | FOOD_EXTRA_SECTORS) - FOOD_EXCLUDED_SECTORS


def get_filter(ext_name, s_name, food_sectors):
    """(axis, sectors kept) for an extension: S_Z_FILTERS for the S_Z
    extensions, otherwise Food columns (+ S_X_DOM_EXTRA_SECTORS)."""
    if s_name == "S_Z":
        if ext_name not in S_Z_FILTERS:
            raise ValueError(f"S_Z extension without a filter defined in S_Z_FILTERS: {ext_name}")
        axis, extra = S_Z_FILTERS[ext_name]
        return axis, food_sectors | extra
    return "columns", food_sectors | S_X_DOM_EXTRA_SECTORS.get(ext_name, set())


def get_extensions(group):
    """Extension -> shocked coefficients: S_x_dom if present, otherwise S_Z
    (extensions in product format, e.g. dom_raw_materials of the France accounts)."""
    extensions = {}
    for ext in sorted(EXTENSIONS_BASE_DIRS[group].iterdir()):
        for s_name in S_NAMES:
            if (ext / f"{s_name}.pkl").is_file():
                extensions[ext.name] = s_name
                break
    return extensions


def compute_ds_agri(ds, axis, kept_sectors):
    """Sectors kept (on the given axis, "columns" or "index"): dS unchanged;
    other sectors: dS = -1 (S = 0)."""
    ds = ds.copy()
    if axis == "index":
        is_kept = ds.index.get_level_values("sector").isin(kept_sectors)
        ds.loc[~is_kept, :] = -1.0
    else:
        is_kept = ds.columns.get_level_values("sector").isin(kept_sectors)
        ds.loc[:, ~is_kept] = -1.0
    return ds


def write_ds(out_dir, ds, ds_name):
    if not isinstance(ds.index, pd.MultiIndex):
        ds.index = pd.MultiIndex.from_arrays([ds.index], names=ds.index.names)
    make_pickle_portable(ds).to_pickle(out_dir / f"{ds_name}.pkl")
    print(f"[write] {out_dir / f'{ds_name}.pkl'}")


def write_extension_agri(group, scenario_dir, ext_name, s_name, info, food_sectors):
    """Rewrites d<s_name> (dS_x_dom or dS_Z) of the extension in scenario_dir
    (_agri folder), from the dS already present (copied from the original
    scenario) or from 0 if there is none."""
    base_ext_dir = EXTENSIONS_BASE_DIRS[group] / ext_name
    out_dir = scenario_dir / "extensions" / ext_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if not (out_dir / "detail_levels.xlsx").exists():
        shutil.copy2(base_ext_dir / "detail_levels.xlsx", out_dir / "detail_levels.xlsx")
    if not (out_dir / "info.json").exists():
        ext_info = {**info, "extension_name": ext_name}
        (out_dir / "info.json").write_text(json.dumps(ext_info, indent=2), encoding="utf-8")

    ds_name = f"d{s_name}"
    ds_path = out_dir / f"{ds_name}.pkl"
    if ds_path.exists():
        ds = pd.read_pickle(ds_path)
    else:
        s_base = pd.read_pickle(base_ext_dir / f"{s_name}.pkl")
        ds = pd.DataFrame(0.0, index=s_base.index, columns=s_base.columns)
    axis, kept_sectors = get_filter(ext_name, s_name, food_sectors)
    write_ds(out_dir, compute_ds_agri(ds, axis, kept_sectors), ds_name)


def check_food_sectors(group, ext_name, s_name, food_sectors):
    s_base = pd.read_pickle(EXTENSIONS_BASE_DIRS[group] / ext_name / f"{s_name}.pkl")
    axis, kept_sectors = get_filter(ext_name, s_name, food_sectors)
    labels = s_base.index if axis == "index" else s_base.columns
    unknown = sorted(kept_sectors - set(labels.get_level_values("sector")))
    if unknown:
        print(f"[warn] {group} / {ext_name} : kept sectors missing from {s_name} ({axis}): {unknown}")


def ignore_data_xlsx(_dir, names):
    """Only the .pkl files are copied for the data; .xlsx kept for detail_levels."""
    return [n for n in names if n.endswith(".xlsx") and n != "detail_levels.xlsx"]


def make_scenario_agri(group, src_dir, out_dir, extensions, food_sectors):
    print(f"=== {out_dir.parent.name} / {out_dir.name} ===")
    shutil.copytree(src_dir, out_dir, ignore=ignore_data_xlsx)
    info = json.loads((out_dir / "system" / "info.json").read_text(encoding="utf-8"))
    for ext_name, s_name in extensions.items():
        write_extension_agri(group, out_dir, ext_name, s_name, info, food_sectors)
    return info


def make_base_year_agri(group, template_dir, out_dir, extensions, food_sectors):
    """Base_year_agri: system without shock, dS = 0 (Food) / -1 (others)."""
    print(f"=== {out_dir.parent.name} / {out_dir.name} ===")
    template_info = json.loads((template_dir / "system" / "info.json").read_text(encoding="utf-8"))
    base_year = template_info["base_year"]
    info = {"base_year": base_year, "proj_year": base_year, "scenario_name": BASE_YEAR_SCENARIO}

    system_dir = out_dir / "system"
    system_dir.mkdir(parents=True)
    shutil.copy2(template_dir / "system" / "detail_levels.xlsx", system_dir / "detail_levels.xlsx")
    (system_dir / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

    for ext_name, s_name in extensions.items():
        ext_dir = out_dir / "extensions" / ext_name
        ext_dir.mkdir(parents=True)
        # detail_levels taken from the original scenario (same resolution as the shocks)
        template_dl = template_dir / "extensions" / ext_name / "detail_levels.xlsx"
        if template_dl.exists():
            shutil.copy2(template_dl, ext_dir / "detail_levels.xlsx")
        write_extension_agri(group, out_dir, ext_name, s_name, info, food_sectors)


def main():
    food_sectors = load_food_sectors()
    print(f"{len(food_sectors)} Food sectors: {sorted(food_sectors)}")

    for group in EXTENSIONS_BASE_DIRS:
        src_group_dir = SHOCKS_DIR / group
        out_group_dir = SHOCKS_DIR / f"{group}{AGRI_SUFFIX}"
        if out_group_dir.exists():
            shutil.rmtree(out_group_dir)
        out_group_dir.mkdir(parents=True)
        if (src_group_dir / "metadata.json").exists():
            shutil.copy2(src_group_dir / "metadata.json", out_group_dir / "metadata.json")

        extensions = get_extensions(group)
        for ext_name, s_name in extensions.items():
            check_food_sectors(group, ext_name, s_name, food_sectors)

        scenario_dirs = sorted(d for d in src_group_dir.iterdir() if d.is_dir())
        for src_dir in scenario_dirs:
            make_scenario_agri(group, src_dir, out_group_dir / f"{src_dir.name}{AGRI_SUFFIX}", extensions, food_sectors)

        make_base_year_agri(group, scenario_dirs[0], out_group_dir / BASE_YEAR_SCENARIO, extensions, food_sectors)


if __name__ == "__main__":
    main()
