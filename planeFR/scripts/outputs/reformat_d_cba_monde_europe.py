"""
For each extension in Outputs/World/Base_year_2015 and Base_year_2019/extensions:
- turns d_cba.pkl / F_x_dom.pkl / F_Y_tot.pkl into World, Europe and one-per-Exiobase-region versions
- World : drops the unwanted Y_categories, sums everything -> (region="World", Y_category="all", sector="all")
- Europe: same but keeping only the first 27 regions -> (region="Europe", ...)
- Region (except FR): same but keeping a single Exiobase region (e.g. "DK"...)
  -> (region=<code>, ...); same files (d_cba/F_x_dom/F_Y_tot) and same tree as
  World/Europe (<ext_name> folder, no dom_ prefix), exported to 2019_<code>
  (one per region listed in detail_levels.xlsx, EU and non-EU)
- France (FR): special case kept as is -- only F_Y_tot.pkl is exported, into
  dom_{ext_name}, because d_cba/F_x_dom for France already come from another
  pipeline (existing dom_/imp_ France scenarios in data/<version>)

The France F_Y_tot of each base year (SRC_DIR / SRC_BASE_YEARS) is copied into
dom_{ext} of every France scenario folder with the SAME base year already
present in data/<version>, whether directly below it (e.g. 2019_FR) or in a
group folder (data/<version>/<group>/<scenario>, e.g. no_SSP/S1_2050,
SSP2_2050/TEND_2050, Base_year/2019_FR). The base year of a folder is read in
its system/info.json (base_year) and not deduced from its location: a copy of
2019_FR placed in a group does get the 2019 F_Y_tot, and the 2050 scenarios
(base year 2015) the 2015 F_Y_tot.

Base_year_2019 (SRC_DIR[1]) also produces the World, Europe and one version per
Exiobase region other than France, each in its own folder (2019_W, 2019_EU27,
2019_<code>).

Agri-food variant: if Outputs/World/Base_year_2019_agri exists (regions_agri
step of planefr.py), it is processed the same way into 2019_W_agri,
2019_EU27_agri and 2019_<code>_agri (REGIONS_agri group of the figures). It
never exports a France F_Y_tot: 2019_FR_agri is a France engine output, which
gets its F_Y_tot like any other France folder of base year 2019.

This script rewrites F_Y_tot.pkl to its base-year value: compute_ds_x_dom.py
(F_Y_tot shocks of the scenarios) must be run after it.
"""

import json
import os
import pickle
import shutil
import sys
from pathlib import Path

import pandas as pd

# Shared modules of planeFR/scripts/_common
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_common"))
import planefr_paths  # noqa: E402

# Paths (relative to this script, not to the current working directory)
PLANEFR_DATA_DIR = str(planefr_paths.PLANEFR_DATA_DIR)

SRC_DIR = [
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "Base_year_2015", "extensions"),
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "Base_year_2019", "extensions"),
]
# Base year of the accounts of each SRC_DIR folder (same order)
SRC_BASE_YEARS = [2015, 2019]

# Module_PlaneFR/data/Outputs_MatMat/<version> (version: environment variable
# PLANEFR_EXIOBASE_VERSION, set by planefr.py from --version)
EXIOBASE_VERSION = planefr_paths.EXIOBASE_VERSION
DATA_DIR = str(planefr_paths.DATA_VERSION_DIR)
# World/Europe/region outputs go to 2019_raw/
RAW_2019_DIR = str(planefr_paths.RAW_2019_DIR)

# Y_categories to exclude. This label ("Exports: Total (fob)") is that of the RAW
# upstream data (SRC_DIR); it must not be confused with the "Exports" label used
# by the analysis notebooks (planefr_lib.io.exclude_y_category), which read the
# data already reformatted in data/<version> -- two stages of the pipeline, two
# different labels for the same concept, not an inconsistency.
YCATS_EXCLUDED = {"Exports: Total (fob)"}

# List of all the Exiobase regions (EU then non-EU / "Rest of World" aggregates)
# from the reference file; the first 27 are the European (EU) regions.
DETAIL_LEVELS_PATH = os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "Base_year_2019", "system", "detail_levels.xlsx")
with open(DETAIL_LEVELS_PATH, "rb") as f:
    _regions_df = pd.read_excel(f, sheet_name="regions")
ALL_REGIONS = _regions_df["region"].astype(str).to_list()
EU_REGIONS = ALL_REGIONS[:27]

# Region handled separately: only F_Y_tot.pkl is exported, into the existing
# France scenario folders (see FRANCE_DIRS)
FRANCE_CODE = "FR"
# Extensions whose France F_Y comes from the France calibration (no F_Y_tot exported)
FRANCE_EXCLUDED_EXTENSIONS = {"ghg_emissions", "raw_materials"}

# Agri-food variant of the 2019 World accounts (optional, see the docstring)
AGRI_SUFFIX = "_agri"
SRC_DIR_AGRI = os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", f"Base_year_2019{AGRI_SUFFIX}", "extensions")


def world_targets(suffix=""):
    """(mode, extensions/ destination) of the World, Europe and regions other
    than France: 2019_W<suffix>, 2019_EU27<suffix>, and one 2019_<code><suffix>
    per Exiobase region other than France (e.g. 2019_DK)."""
    return [("monde", os.path.join(RAW_2019_DIR, f"2019_W{suffix}", "extensions")),
            ("europe", os.path.join(RAW_2019_DIR, f"2019_EU27{suffix}", "extensions"))] + [
        (code, os.path.join(RAW_2019_DIR, f"2019_{code}{suffix}", "extensions"))
        for code in ALL_REGIONS if code != FRANCE_CODE]


# Output folders entirely produced by this script (World, Europe, regions other
# than France, and their _agri variants): never France scenarios.
EXCLUDED_DIRS = {os.path.basename(os.path.dirname(dst))
                 for suffix in ("", AGRI_SUFFIX) for _mode, dst in world_targets(suffix)}


def _find_scenario_extension_dirs(data_dir: str) -> list[str]:
    """Lists the extensions/ folders of every scenario of data/<version>
    (2019_raw/<scenario>, 2050_raw/<group>/<scenario>, display groups), except
    the output folders of this script (EXCLUDED_DIRS). data_dir is kept for
    compatibility: the tree is that of planefr_paths.find_all_scenario_dirs."""
    return [
        str(d / "extensions") for d in planefr_paths.find_all_scenario_dirs()
        if d.name not in EXCLUDED_DIRS
    ]


def _is_france_scenario(extensions_dir: str) -> bool:
    """True if the extensions are split into dom_<ext> / imp_<ext> (outputs of
    the France engine), unlike the World/Europe/region folders (a single <ext>
    folder), including a possible copy of those in a group."""
    return any(d.startswith(("dom_", "imp_")) for d in os.listdir(extensions_dir))


def _scenario_base_year(extensions_dir: str) -> int:
    """Base year of a France scenario: base_year of its system/info.json. Failing
    that (missing or incomplete file), 2019 if the folder name contains "2019",
    2015 otherwise."""
    scenario_dir = os.path.dirname(extensions_dir)
    try:
        with open(os.path.join(scenario_dir, "system", "info.json"), encoding="utf-8-sig") as f:
            return int(json.load(f)["base_year"])
    except (OSError, KeyError, TypeError, ValueError):
        year = 2019 if "2019" in os.path.basename(scenario_dir) else 2015
        print(f"[warn] {scenario_dir} : base_year unreadable in system/info.json, {year} deduced from the folder name")
        return year


def _is_agri_scenario(extensions_dir: str) -> bool:
    """True for an agri-food folder: the scenario or one of its parent folders
    (group) ends with _agri, e.g. 2050_raw/no_SSP_agri/S1_2050_agri,
    2019_raw/2019_FR_agri, CONF_agri/S1."""
    relative = os.path.relpath(os.path.dirname(extensions_dir), DATA_DIR)
    return any(part.endswith(AGRI_SUFFIX) for part in Path(relative).parts)


def _find_france_dirs_by_base_year(data_dir: str) -> dict[int, list[str]]:
    """{base year: [extensions/ folders of the France scenarios of that year]},
    for the years of SRC_BASE_YEARS. The agri-food folders are left out: they
    take no F_Y_tot (direct emissions of final demand, outside the agri-food
    system; see remove_agri_f_y_tot)."""
    by_year = {year: [] for year in SRC_BASE_YEARS}
    for extensions_dir in _find_scenario_extension_dirs(data_dir):
        if not _is_france_scenario(extensions_dir) or _is_agri_scenario(extensions_dir):
            continue
        year = _scenario_base_year(extensions_dir)
        if year in by_year:
            by_year[year].append(extensions_dir)
        else:
            print(f"[warn] {extensions_dir} : base year {year} without World accounts (SRC_BASE_YEARS), F_Y_tot not exported")
    return by_year


# France scenario folders already present in data/<version>, by base year
FRANCE_DIRS = _find_france_dirs_by_base_year(DATA_DIR)


def transform(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """
    mode='monde'  -> all regions except the excluded Y_cats, summed -> World/all/all
    mode='europe' -> first 27 regions except the excluded Y_cats, summed -> Europe/all/all
    mode=<code>   -> a single Exiobase region (e.g. 'FR', 'DK'...), summed -> <code>/all/all
    """
    if "Y_category" in df.columns.names:
        mask_ycat = ~df.columns.get_level_values("Y_category").isin(YCATS_EXCLUDED)
        df = df.loc[:, mask_ycat]

    if mode == "europe":
        df = df.loc[:, df.columns.get_level_values("region").isin(EU_REGIONS)]
    elif mode != "monde":
        df = df.loc[:, df.columns.get_level_values("region") == mode]

    totals = df.sum(axis=1)

    region_label = {"monde": "World", "europe": "Europe"}.get(mode, mode)
    if "Y_category" in df.columns.names:
        col_index = pd.MultiIndex.from_tuples([(region_label, "all", "all")], names=["region", "Y_category", "sector"])
    else:
        col_index = pd.MultiIndex.from_tuples([(region_label, "all")], names=["region", "sector"])

    return pd.DataFrame(totals.values, index=df.index, columns=col_index)


def _save_result(out_dir, filename, result, label):
    """Writes `result` as a pickle to out_dir/filename (creating the missing folders), with a log line."""
    os.makedirs(out_dir, exist_ok=True)
    out_pkl = os.path.join(out_dir, filename)
    with open(out_pkl, "wb") as f:
        pickle.dump(result, f)
    print(f"  [{label.upper()}] {out_pkl}  shape={result.shape}")


def process_extension(ext_name: str, src_dir: str):
    if src_dir == SRC_DIR_AGRI:
        _export_world_targets(ext_name, src_dir, AGRI_SUFFIX)
        return
    base_year = SRC_BASE_YEARS[SRC_DIR.index(src_dir)]
    srcs_pkl = [
        os.path.join(src_dir, ext_name, "d_cba.pkl"),
        os.path.join(src_dir, ext_name, "F_x_dom.pkl"),
        os.path.join(src_dir, ext_name, "F_Y_tot.pkl"),
    ]

    for src_pkl, filename, df in _load_sources(ext_name, src_dir):
        # France: only F_Y_tot.pkl is exported, into dom_<ext> of each France
        # scenario folder whose base year is that of these World accounts
        # (2015: base years and 2050 scenarios; 2019: 2019_FR and its copies).
        if filename == "F_Y_tot.pkl" and ext_name not in FRANCE_EXCLUDED_EXTENSIONS:
            result = transform(df, FRANCE_CODE)
            for path in FRANCE_DIRS[base_year]:
                _save_result(os.path.join(path, f"dom_{ext_name}"), filename, result, FRANCE_CODE)

        # World, Europe and regions other than France: produced from
        # Base_year_2019 only (the 3 files, <ext_name> folder without dom_ prefix).
        if src_dir == SRC_DIR[1]:
            _export_world_targets_df(ext_name, filename, df, "")


def _export_world_targets(ext_name: str, src_dir: str, suffix: str):
    """World, Europe and regions other than France of src_dir, into the
    2019_*<suffix> folders (no France F_Y_tot export)."""
    for _src_pkl, filename, df in _load_sources(ext_name, src_dir):
        if filename == "F_Y_tot.pkl":
            continue  # no direct emissions of final demand in the agri-food variant
        _export_world_targets_df(ext_name, filename, df, suffix)


def _export_world_targets_df(ext_name, filename, df, suffix):
    for mode, dst_base in world_targets(suffix):
        _save_result(os.path.join(dst_base, ext_name), filename, transform(df, mode), mode + suffix)


def _load_sources(ext_name: str, src_dir: str):
    """(path, file name, cleaned DataFrame) of the d_cba / F_x_dom / F_Y_tot
    pickles of an extension of src_dir."""
    for name in ("d_cba.pkl", "F_x_dom.pkl", "F_Y_tot.pkl"):
        src_pkl = os.path.join(src_dir, ext_name, name)
        if not os.path.exists(src_pkl):
            print(f"  [SKIP] {name} not found in {ext_name}")
            continue

        with open(src_pkl, "rb") as f:
            df = pickle.load(f)

        # Some extensions (e.g. raw_materials) come with a single-level MultiIndex
        # (each key is a tuple ('Primary Crops - Rice',)) instead of a flat Index
        # of strings ('Primary Crops - Rice'). This is an artefact of
        # cast_index_to_multiindex() in the extraction pipeline (its counterpart
        # convert_single_level_multi_index_to_regular_index() is never called);
        # it is undone here so that the exported index is flat.
        if isinstance(df.index, pd.MultiIndex) and df.index.nlevels == 1:
            df.index = df.index.get_level_values(0)

        if "source" in df.index.names:
            df = df.groupby(level="gas").sum()
            df.index.name = "indicator"

        if "Primary Crops - Rice" in df.index and "RMC" not in df.index:
            total = df.sum().rename("RMC").to_frame().T
            total.index.name = "indicator"
            df = pd.concat([df, total])

        yield src_pkl, name, df


def _source_dirs():
    """World accounts processed: SRC_DIR, plus SRC_DIR_AGRI if it exists."""
    if os.path.isdir(SRC_DIR_AGRI):
        return SRC_DIR + [SRC_DIR_AGRI]
    print(f"[info] {SRC_DIR_AGRI} not found: no 2019_*{AGRI_SUFFIX} folder (run planefr.py --Agri)")
    return list(SRC_DIR)


def _clean_generated_outputs(suffixes=("",)):
    """Deletes the whole extensions/ folder of each World/Europe/region output
    other than France (2019_W<suffix>, 2019_EU27<suffix>, 2019_<code><suffix>)
    before regenerating it -- only for the suffixes whose source exists, so that
    the _agri folders are kept when Base_year_2019_agri is missing.

    These folders are entirely produced by this script: they can therefore be
    recreated from scratch without losing external data. The France scenario
    folders (FRANCE_DIRS, including 2019_FR) are never deleted: they already
    contain dom_{ext}/imp_{ext} sub-folders (d_cba.pkl, F_x_dom.pkl...) coming
    from the France engine, into which this script only adds
    dom_{ext}/F_Y_tot.pkl. Deleting them would erase this external data (it
    happened: a previous run overwrote 2019_FR that way).
    """
    for suffix in suffixes:
        for _mode, dst_base in world_targets(suffix):
            if os.path.isdir(dst_base):
                shutil.rmtree(dst_base)


def remove_agri_f_y_tot():
    """Deletes the F_Y_tot.pkl of the agri-food folders (France and regions):
    the direct emissions of final demand (household heating, cars...) are not
    part of the agri-food system. Removes those written by earlier runs."""
    for d in planefr_paths.find_all_scenario_dirs():
        extensions_dir = d / "extensions"
        if not extensions_dir.is_dir() or not _is_agri_scenario(str(extensions_dir)):
            continue
        for f_y_tot in extensions_dir.glob("*/F_Y_tot.pkl"):
            f_y_tot.unlink()
            print(f"  [AGRI] F_Y_tot removed: {f_y_tot}")


def main():
    remove_agri_f_y_tot()
    src_dirs = _source_dirs()
    _clean_generated_outputs(("", AGRI_SUFFIX) if SRC_DIR_AGRI in src_dirs else ("",))

    for src_dir in src_dirs:
        extensions = [
            d for d in os.listdir(src_dir)
        ]
        print(f"{len(extensions)} extension(s) found: {extensions}\n")

        for ext in extensions:
            print(f"--- {ext} ---")
            process_extension(ext, src_dir)
            print()

    print("Done.")


if __name__ == "__main__":
    main()
