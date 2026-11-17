"""
Rebuilds, for a shock scenario (e.g. .../2-shocks/1-transitions_2050/S1_2050),
the extensions/dom_<ext> sub-folders from the outputs of gmrio_to_snac_s.

For each extension <ext>:
    - detail_levels.xlsx: dom_<ext> sheet (extension categories) taken from
      <gmrio_dir>/extensions/dom_<ext>/detail_levels.xlsx, followed by the
      regions / sectors / final_demand_categories sheets of the scenario
      (<scenario_dir>/system/detail_levels.xlsx), because the system of the
      scenario does not have the same resolution as that of gmrio_to_snac_s;
    - info.json: base_year / proj_year / scenario_name taken from
      <scenario_dir>/system/info.json, plus extension_name = dom_<ext>.

Prior cleaning of the <scenario_dir>/extensions folder (prepare_extensions_dir):
    - the sub-folders that will not be rebuilt (extensions removed from the
      list, or EXCLUDED_EXTENSIONS) are deleted;
    - in the others, all the files are deleted EXCEPT the dS_* extension
      shocks (dS_x_dom.pkl/.xlsx written by compute_ds_x_dom.py).

Keeping the dS_x_dom lets the engine apply them from the first pass of
run_full_pipeline.ps1 (values of the previous run), instead of running
without extension shocks. compute_ds_x_dom.py rewrites them (or deletes them
if they have become zero) at the end of each pass.

Usage:
    python rebuild_shock_extensions.py --scenario-dir <dir> --gmrio-dir <dir>
        --extensions ext1 ext2 ...
"""

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

DL_FILE = "detail_levels.xlsx"
INFO_FILE = "info.json"
# Prefix of the extension shock files kept by prepare_extensions_dir
KEPT_FILE_PREFIX = "dS_"

# Extensions taken from the older accounts by update_calib_fr: their
# categories do not match those of gmrio_to_snac_s, so they are not rebuilt
# (otherwise the engine raises MEInconsistentDetailLevels).
EXCLUDED_EXTENSIONS = {"raw_materials", "ghg_emissions"}


def prepare_extensions_dir(scenario_dir: Path, ext_names: set):
    """Empties <scenario_dir>/extensions before rebuilding, keeping the dS_*
    files of the extensions of ext_names (dom_<ext> names); the sub-folders of
    the other extensions are deleted entirely."""
    extensions_dir = scenario_dir / "extensions"
    if not extensions_dir.is_dir():
        return
    for sub in extensions_dir.iterdir():
        if not sub.is_dir() or sub.name not in ext_names:
            shutil.rmtree(sub) if sub.is_dir() else sub.unlink()
            continue
        for item in sub.iterdir():
            if item.is_file() and item.name.startswith(KEPT_FILE_PREFIX):
                print(f"  {scenario_dir.name} : {sub.name}/{item.name} kept")
                continue
            shutil.rmtree(item) if item.is_dir() else item.unlink()


def rebuild_extension(scenario_dir: Path, gmrio_dir: Path, extension: str):
    ext_name = f"dom_{extension}"
    gmrio_dl = gmrio_dir / "extensions" / ext_name / DL_FILE
    if not gmrio_dl.is_file():
        raise FileNotFoundError(f"Detail levels not found: {gmrio_dl}")

    ext_categories = pd.read_excel(gmrio_dl, sheet_name=ext_name)
    system_sheets = pd.read_excel(scenario_dir / "system" / DL_FILE, sheet_name=None)
    system_info = json.loads((scenario_dir / "system" / INFO_FILE).read_text(encoding="utf-8"))

    ext_dir = scenario_dir / "extensions" / ext_name
    ext_dir.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ext_dir / DL_FILE, engine="openpyxl") as writer:
        ext_categories.to_excel(writer, sheet_name=ext_name, index=False)
        for sheet_name, df in system_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    info = {**system_info, "extension_name": ext_name}
    (ext_dir / INFO_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-dir", required=True, type=Path)
    parser.add_argument("--gmrio-dir", required=True, type=Path)
    parser.add_argument("--extensions", required=True, nargs="+")
    args = parser.parse_args()

    rebuilt = {f"dom_{ext}" for ext in args.extensions if ext not in EXCLUDED_EXTENSIONS}
    prepare_extensions_dir(args.scenario_dir, rebuilt)

    for extension in args.extensions:
        if extension in EXCLUDED_EXTENSIONS:
            print(f"  {args.scenario_dir.name} : dom_{extension} skipped")
            continue
        rebuild_extension(args.scenario_dir, args.gmrio_dir, extension)
        print(f"  {args.scenario_dir.name} : dom_{extension} rebuilt")


if __name__ == "__main__":
    main()
