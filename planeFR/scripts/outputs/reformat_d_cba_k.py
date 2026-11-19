"""
One-off reformatting of the France extensions (raw output of the CIRED/MatMat
pipeline, INPUT folder) into data/<version>/. The files are looked for in each
extensions/ folder (find_files), so every scenario is processed, whether
directly under data/<version>/<scenario> or nested by SSP
(data/<version>/<SSP>/<scenario>, e.g. no_SSP/S1_2050, SSP1_2050/TEND_2050).
Each step is idempotent: an already reformatted file is rewritten identically.
Treatments:

- ghg_emissions: removes the ghg_combustion part (handled separately below),
  renames the "gas" index level to "indicator".
- ghg_combustion: collapses into a single "CO2" row; imp_ghg_combustion does
  not exist upstream, it is created filled with zeros (combustion emissions are
  100% domestic by construction).
- raw_materials: keeps all the rows (indexed by "indicator", at the "sector"
  level) and adds an "RMC" row = sum of all the raw materials.
- F_x_dom of ghg_combustion and raw_materials: these two extensions have no
  F_x_dom.pkl provided upstream; it is recomputed from F_Z.pkl / F_Y.pkl, whose
  rows are the products burned / extracted and the columns the using sectors /
  final demand:
    * raw_materials: domestic rows of F_Y + F_Z (extraction on the French
      territory), in the same format as the other F_x_dom: one row per
      material (non-zero only in the column of the extracting sector of the
      same name) + an "RMC" row = sum, x 200 sectors;
    * ghg_combustion: territorial emissions, whatever the origin of the fuel
      (domestic or imported). F_x_dom = column sums of F_Z over all the rows
      (1 "CO2" row x 200 sectors: direct emissions of the sector that BURNS the
      fuel); the combustion by households (F_Y, all rows) goes into
      dom_ghg_combustion/F_Y_tot.pkl (PBA). d_cba already includes this F_Y
      (computed with S_Y): PlaneFR does not add F_Y_tot to the CBA of an
      extension with an S_Y.pkl. No F_Y_tot in the agri-food folders (direct
      emissions of final demand outside the agri-food system, see
      reformat_d_cba_monde_europe.remove_agri_f_y_tot).
    Previously, ghg_combustion was also restricted to the domestic rows: the
    CO2 of the imported fuels burned in France was missing from the PBA (2015:
    120 instead of 301).
- M, M_k (and M_RoW on the imp side): rows reformatted like those of d_cba.
- S_x_dom (ghg_emissions), S_Y / S_Z (ghg_combustion, raw_materials): rows
  reformatted like those of F_x_dom (domestic part only).
"""

import os
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Shared modules of planeFR/scripts/_common
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_common"))

# Module_PlaneFR/data/Outputs_MatMat/<version> (version: environment variable
# PLANEFR_EXIOBASE_VERSION, set by planefr.py from --version)
from planefr_paths import DATA_VERSION_DIR, find_all_scenario_dirs

INPUT = DATA_VERSION_DIR
OUTPUT = INPUT

# extensions/ folders of all the scenarios (2019_raw, 2050_raw and display
# groups), listed once: an rglob over the whole INPUT for each file pattern
# would walk the full tree at each call (very slow).
EXTENSION_DIRS = sorted(d / "extensions" for d in find_all_scenario_dirs())


def find_files(pattern):
    """Files matching `pattern` (e.g. "dom_ghg_emissions/d_cba.pkl",
    "*raw_materials/M.pkl") in each of the EXTENSION_DIRS folders."""
    return [p for ext_dir in EXTENSION_DIRS for p in ext_dir.glob(pattern)]


def collapse_to_single_row(df, label):
    """Collapses all the rows of df into a single one, named `label` (e.g. "CO2", "RMC")."""
    collapsed = df.sum().rename(label).to_frame().T
    collapsed.index.name = "indicator"
    return collapsed


def add_sum_row(df, label):
    """Reduces the index to its last level (the "sector", renamed "indicator")
    if needed, keeping all the rows, and adds a `label` row equal to their sum
    (e.g. "RMC" = sum of all the raw materials)."""
    if df.index.nlevels > 1:
        df = df.set_index(df.index.get_level_values(-1))
    df.index.name = "indicator"

    if label in df.index:
        return df

    total = df.sum().rename(label).to_frame().T
    total.index.name = "indicator"
    return pd.concat([df, total])


def save_pickle(df, out_path, note=""):
    """Writes df as a pickle to out_path (creating the missing folders) and logs the result."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(df, f)
    label = f"Done ({note})" if note else "Done"
    print(f"{label}: {out_path.relative_to(OUTPUT)}  shape={df.shape}  index={df.index.names}")


def compute_raw_materials_f_x_dom(label="RMC"):
    """F_x_dom.pkl of dom_raw_materials (extraction on the French territory),
    from F_Z.pkl + F_Y.pkl (rows = products extracted, domestic and imported;
    columns = using sectors / final demand), in the same format as the other
    F_x_dom (rows = indicators, columns = the 200 domestic sectors):
      - one row per material i (indexed by its name, "indicator"): extraction
        of i = sum of the domestic row i of F_Z + F_Y, placed in the column of
        the extracting sector (the domestic sector i), 0 elsewhere;
      - a `label` row ("RMC") = sum of all the materials, by sector.
    The domestic rows of F_Z / F_Y are in the same order as the columns of F_Z
    (checked, otherwise error)."""
    for f_z_path in sorted(find_files("dom_raw_materials/F_Z.pkl")):
        ext_dir = f_z_path.parent
        with open(f_z_path, "rb") as f:
            f_z = pickle.load(f)
        extracted = f_z[f_z.index.get_level_values("origin") == "domestic"].droplevel("origin").sum(axis=1)
        f_y_path = ext_dir / "F_Y.pkl"
        if f_y_path.exists():
            with open(f_y_path, "rb") as f:
                f_y = pickle.load(f)
            extracted = extracted.add(
                f_y[f_y.index.get_level_values("origin") == "domestic"].droplevel("origin").sum(axis=1),
                fill_value=0,
            )
        if not extracted.index.equals(f_z.columns):
            extracted = extracted.reindex(f_z.columns)
            if extracted.isna().any():
                raise ValueError(f"{ext_dir}: domestic rows of F_Z/F_Y do not match its columns")

        f_x_dom = pd.DataFrame(
            np.diag(extracted.to_numpy(dtype=float)),
            index=pd.Index(f_z.columns.get_level_values(-1), name="indicator"),
            columns=f_z.columns,
        )
        f_x_dom.loc[label] = f_x_dom.sum(axis=0)
        save_pickle(f_x_dom, OUTPUT / ext_dir.relative_to(INPUT) / "F_x_dom.pkl", note="materials x sectors")


AGRI_SUFFIX = "_agri"


def is_agri_scenario(scenario_dir):
    """True for an agri-food folder: the scenario or one of its parent folders
    (group) ends with _agri (same rule as reformat_d_cba_monde_europe)."""
    return any(part.endswith(AGRI_SUFFIX) for part in scenario_dir.relative_to(INPUT).parts)


def compute_ghg_combustion_f_x_dom_and_f_y_tot(label="CO2"):
    """Territorial combustion emissions of dom_ghg_combustion, all fuels
    (domestic and imported), from F_Z.pkl / F_Y.pkl (rows = products burned,
    columns = using sectors / final demand):
      - F_x_dom.pkl: column sums of F_Z -> 1 `label` row x 200 sectors (sector
        that burns the fuel), same format as the other F_x_dom;
      - F_Y_tot.pkl: sum of F_Y (combustion by households) -> 1 `label` row x
        ("FR", "all"), same format as the France F_Y_tot of the other
        extensions. Not written in the agri-food folders (and removed there if
        present)."""
    for f_z_path in sorted(find_files("dom_ghg_combustion/F_Z.pkl")):
        ext_dir = f_z_path.parent
        scenario_dir = ext_dir.parent.parent
        with open(f_z_path, "rb") as f:
            f_z = pickle.load(f)

        f_x_dom = f_z.sum(axis=0).rename(label).to_frame().T
        f_x_dom.index.name = "indicator"
        save_pickle(f_x_dom, OUTPUT / ext_dir.relative_to(INPUT) / "F_x_dom.pkl", note="all fuels, by burning sector")

        f_y_path = ext_dir / "F_Y.pkl"
        f_y_tot_path = OUTPUT / ext_dir.relative_to(INPUT) / "F_Y_tot.pkl"
        if is_agri_scenario(scenario_dir):
            if f_y_tot_path.exists():
                f_y_tot_path.unlink()
                print(f"  [AGRI] F_Y_tot removed: {f_y_tot_path.relative_to(OUTPUT)}")
            continue
        if f_y_path.exists():
            with open(f_y_path, "rb") as f:
                f_y = pickle.load(f)
            f_y_tot = pd.DataFrame(
                [[float(f_y.to_numpy().sum())]],
                index=pd.Index([label], name="indicator"),
                columns=pd.MultiIndex.from_tuples([("FR", "all")], names=["region", "sector"]),
            )
            save_pickle(f_y_tot, f_y_tot_path, note="households, all fuels")


def reformat_s_like_f_x_dom(extension_name, label, keep_detail=False):
    """Reformats the rows of S_Y.pkl / S_Z.pkl like those of F_x_dom.pkl:
    domestic part only, then either collapsed into a single `label` row
    (ghg_combustion: "CO2"), or one row per raw material + a `label` row = sum
    (raw_materials: "RMC"). The columns are kept."""
    for in_path in sorted([
        *find_files(f"dom_{extension_name}/S_Y.pkl"),
        *find_files(f"dom_{extension_name}/S_Z.pkl"),
    ]):
        with open(in_path, "rb") as f:
            df = pickle.load(f)

        if "origin" in df.index.names:
            df = df[df.index.get_level_values("origin") == "domestic"]
            df = df.droplevel("origin")

        if keep_detail:
            df = add_sum_row(df, label)
        elif label not in df.index:
            df = collapse_to_single_row(df, label)

        save_pickle(df, OUTPUT / in_path.relative_to(INPUT))


# --- 1a. dom_ghg_emissions: drop ghg_combustion, droplevel source, rename gas -> indicator ---
for in_path in sorted([
    *find_files("dom_ghg_emissions/d_cba_k.pkl"),
    *find_files("dom_ghg_emissions/d_cba.pkl"),
    *find_files("dom_ghg_emissions/F_x_dom.pkl"),
    *find_files("dom_ghg_emissions/M.pkl"),
    *find_files("dom_ghg_emissions/M_k.pkl"),
    *find_files("dom_ghg_emissions/S_x_dom.pkl"),
]):
    with open(in_path, "rb") as f:
        df = pickle.load(f)

    if "source" in df.index.names:
        df = df.drop(index="ghg_combustion", level="source")
        df = df.droplevel("source")
        df.index.names = ["indicator" if n == "gas" else n for n in df.index.names]

    save_pickle(df, OUTPUT / in_path.relative_to(INPUT))

# --- 1b. imp_ghg_emissions: sum sources by gas, rename gas -> indicator ---
for in_path in sorted([
    *find_files("imp_ghg_emissions/d_cba_k.pkl"),
    *find_files("imp_ghg_emissions/d_cba.pkl"),
    *find_files("imp_ghg_emissions/M.pkl"),
    *find_files("imp_ghg_emissions/M_k.pkl"),
    *find_files("imp_ghg_emissions/M_RoW.pkl"),
]):
    with open(in_path, "rb") as f:
        df = pickle.load(f)

    if "source" in df.index.names:
        df = df.groupby(level="gas").sum()
        df.index.name = "indicator"

    save_pickle(df, OUTPUT / in_path.relative_to(INPUT))

# --- 2. dom_ghg_combustion: sum -> "CO2", create imp_ghg_combustion with zeros ---
for in_path in sorted([
    *find_files("dom_ghg_combustion/d_cba_k.pkl"),
    *find_files("dom_ghg_combustion/d_cba.pkl"),
    *find_files("dom_ghg_combustion/M.pkl"),
    *find_files("dom_ghg_combustion/M_k.pkl"),
]):
    with open(in_path, "rb") as f:
        df = pickle.load(f)

    if "CO2" not in df.index:
        df = collapse_to_single_row(df, "CO2")

    out_path = OUTPUT / in_path.relative_to(INPUT)
    save_pickle(df, out_path)

    imp_path = Path(str(out_path).replace("dom_ghg_combustion", "imp_ghg_combustion"))
    save_pickle(df * 0, imp_path, note="imp zeros")

compute_ghg_combustion_f_x_dom_and_f_y_tot("CO2")
reformat_s_like_f_x_dom("ghg_combustion", "CO2")

# --- 3. *_raw_materials: keep all the rows, add "RMC" = sum ---
for in_path in sorted([
    *find_files("*raw_materials/d_cba_k.pkl"),
    *find_files("*raw_materials/d_cba.pkl"),
    *find_files("*raw_materials/M.pkl"),
    *find_files("*raw_materials/M_k.pkl"),
    *find_files("imp_raw_materials/M_RoW.pkl"),
]):
    with open(in_path, "rb") as f:
        df = pickle.load(f)

    df = add_sum_row(df, "RMC")

    save_pickle(df, OUTPUT / in_path.relative_to(INPUT))

compute_raw_materials_f_x_dom("RMC")
reformat_s_like_f_x_dom("raw_materials", "RMC", keep_detail=True)
