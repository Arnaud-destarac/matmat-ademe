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
  F_x_dom.pkl provided upstream; it is recomputed from F_Y.pkl + F_Z.pkl
  (domestic part only), collapsed in the same way.
- M, M_k (and M_RoW on the imp side): rows reformatted like those of d_cba.
- S_x_dom (ghg_emissions), S_Y / S_Z (ghg_combustion, raw_materials): rows
  reformatted like those of F_x_dom (domestic part only).
"""

import os
import pickle
import sys
from collections import defaultdict
from pathlib import Path
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


def compute_f_x_dom_from_f_y_f_z(extension_name, label, keep_detail=False):
    """Recomputes F_x_dom.pkl (production footprint, domestic part) from
    F_Y.pkl + F_Z.pkl, for an extension that has no F_x_dom.pkl provided
    directly upstream. If keep_detail=False, collapses the index into a single
    `label` row (ghg_combustion: "CO2"). If keep_detail=True, keeps one row per
    raw material (indexed by "indicator", at the "sector" level) and adds a
    `label` row = sum (raw_materials: "RMC")."""
    paths_by_scenario = defaultdict(list)
    for in_path in sorted([
        *find_files(f"dom_{extension_name}/F_Y.pkl"),
        *find_files(f"dom_{extension_name}/F_Z.pkl"),
    ]):
        paths_by_scenario[in_path.parent.parent].append(in_path)

    for scenario_dir, paths in paths_by_scenario.items():
        f_x_dom = pd.DataFrame()
        for in_path in paths:
            with open(in_path, "rb") as f:
                df = pickle.load(f)
            df = df[df.index.get_level_values("origin") == "domestic"]
            df = df.droplevel("origin")

            if keep_detail:
                if df.index.nlevels > 1:
                    df = df.set_index(df.index.get_level_values(-1))
                    df.index.name = "indicator"
                df = df.sum(axis=1).groupby(level="indicator").sum().to_frame()
            elif label not in df.index:
                df = collapse_to_single_row(df, label).sum(axis=1).to_frame()

            f_x_dom = f_x_dom.add(df, fill_value=0)

        if keep_detail and label not in f_x_dom.index:
            f_x_dom = add_sum_row(f_x_dom, label)

        out_path = OUTPUT / scenario_dir.relative_to(INPUT) / f"dom_{extension_name}" / "F_x_dom.pkl"
        save_pickle(f_x_dom, out_path)


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

compute_f_x_dom_from_f_y_f_z("ghg_combustion", "CO2")
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

compute_f_x_dom_from_f_y_f_z("raw_materials", "RMC", keep_detail=True)
reformat_s_like_f_x_dom("raw_materials", "RMC", keep_detail=True)
