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

This script rewrites F_Y_tot.pkl to its base-year value: compute_ds_x_dom.py
(F_Y_tot shocks of the scenarios) must be run after it.
"""

import json
import os
import pickle
import shutil
import pandas as pd

# Paths (relative to this script, not to the current working directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLANEFR_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "4-PlaneFR")

SRC_DIR = [
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "Base_year_2015", "extensions"),
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "Base_year_2019", "extensions"),
]
# Base year of the accounts of each SRC_DIR folder (same order)
SRC_BASE_YEARS = [2015, 2019]

# Exiobase version (environment variable PLANEFR_EXIOBASE_VERSION, set by
# run_full_pipeline.ps1 / run_pipeline_from_engine.ps1)
EXIOBASE_VERSION = os.environ.get("PLANEFR_EXIOBASE_VERSION", "3.11.2")
DATA_DIR = os.path.join("C:\\Users\\Arnaud\\Documents\\CIRED\\PlaneFR\\Code\\Module_PlaneFR\\data", EXIOBASE_VERSION)
DST_MONDE = os.path.join(DATA_DIR, "2019_W", "extensions")
DST_EUROPE = os.path.join(DATA_DIR, "2019_EU27", "extensions")

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

# One 2019_<code>/extensions destination per Exiobase region other than France (e.g. 2019_DK...)
REGION_TARGETS = [
    (code, os.path.join(DATA_DIR, f"2019_{code}", "extensions")) for code in ALL_REGIONS if code != FRANCE_CODE
]

# Output folders entirely produced by this script (World, Europe, regions other
# than France): never France scenarios.
EXCLUDED_DIRS = {"2019_W", "2019_EU27"} | {f"2019_{code}" for code in ALL_REGIONS if code != FRANCE_CODE}


def _find_scenario_extension_dirs(data_dir: str) -> list[str]:
    """Lists the <scenario>/extensions and <group>/<scenario>/extensions folders
    of data_dir, except the output folders of this script (EXCLUDED_DIRS). Two
    trees coexist:
    - data/<version>/<scenario>/extensions          (e.g. 2019_FR)
    - data/<version>/<group>/<scenario>/extensions  (e.g. no_SSP/S1_2050, Base_year/2019_FR)
    """
    found = []
    for d in sorted(os.listdir(data_dir)):
        top = os.path.join(data_dir, d)
        if d in EXCLUDED_DIRS or not os.path.isdir(top):
            continue
        if os.path.isdir(os.path.join(top, "extensions")):
            found.append(os.path.join(top, "extensions"))
            continue
        for sub in sorted(os.listdir(top)):
            if os.path.isdir(os.path.join(top, sub, "extensions")):
                found.append(os.path.join(top, sub, "extensions"))
    return found


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


def _find_france_dirs_by_base_year(data_dir: str) -> dict[int, list[str]]:
    """{base year: [extensions/ folders of the France scenarios of that year]},
    for the years of SRC_BASE_YEARS."""
    by_year = {year: [] for year in SRC_BASE_YEARS}
    for extensions_dir in _find_scenario_extension_dirs(data_dir):
        if not _is_france_scenario(extensions_dir):
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
    base_year = SRC_BASE_YEARS[SRC_DIR.index(src_dir)]
    srcs_pkl = [
        os.path.join(src_dir, ext_name, "d_cba.pkl"),
        os.path.join(src_dir, ext_name, "F_x_dom.pkl"),
        os.path.join(src_dir, ext_name, "F_Y_tot.pkl"),
    ]

    for src_pkl in srcs_pkl:
        if not os.path.exists(src_pkl):
            print(f"  [SKIP] {os.path.basename(src_pkl)} not found in {ext_name}")
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

        filename = os.path.basename(src_pkl)

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
            for mode, dst_base in [("monde", DST_MONDE), ("europe", DST_EUROPE)] + REGION_TARGETS:
                _save_result(os.path.join(dst_base, ext_name), filename, transform(df, mode), mode)


def _clean_generated_outputs():
    """Deletes the whole extensions/ folder of each World/Europe/region output
    other than France (2019_W, 2019_EU27, 2019_<code>) before regenerating it.

    These folders are entirely produced by this script: they can therefore be
    recreated from scratch without losing external data. The France scenario
    folders (FRANCE_DIRS, including 2019_FR) are never deleted: they already
    contain dom_{ext}/imp_{ext} sub-folders (d_cba.pkl, F_x_dom.pkl...) coming
    from the France engine, into which this script only adds
    dom_{ext}/F_Y_tot.pkl. Deleting them would erase this external data (it
    happened: a previous run overwrote 2019_FR that way).
    """
    for _mode, dst_base in [("monde", DST_MONDE), ("europe", DST_EUROPE)] + REGION_TARGETS:
        if os.path.isdir(dst_base):
            shutil.rmtree(dst_base)


def main():
    _clean_generated_outputs()

    for src_dir in SRC_DIR:
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
