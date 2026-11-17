"""
Extracts the data of Base_year_2015 (system/x.pkl + extensions dom_*/F_x_dom.pkl
and dom_*/F_Y_tot.pkl) into an Excel workbook, one sheet per table.

Sheets produced:
- "x": x.pkl of Base_year_2015, transposed (sectors as columns, like F_x_dom),
  with one additional row per 2050 scenario (S1-S4, TEND) for comparison.
  The "scenario" column gives the name of the source folder of each row.
- "Fx_<lp>": F_x_dom.pkl of each dom_* extension of Base_year_2015
  (indicators as rows, sectors as columns, original format).
- "FY_<lp>": F_Y_tot.pkl of each dom_* extension of Base_year_2015, when this
  file exists (missing for ghg_combustion, ghg_emissions, raw_materials).
"""

import sys
from pathlib import Path

import pandas as pd

MODULE_PLANEFR_DIR = Path(r"C:\Users\Arnaud\Documents\CIRED\PlaneFR\Code\Module_PlaneFR")

sys.path.insert(0, str(MODULE_PLANEFR_DIR / "notebooks"))
from planefr_lib import config  # noqa: E402

BASE_YEAR_FOLDER = config.BASE_DATA_DIR / "no_SSP" / "Base_year_2015"
OTHER_SCENARIO_FOLDERS = [
    d for d in config.get_scenario_folders(exclude_2019=True) if d.name != BASE_YEAR_FOLDER.name
]

OUTPUT_FILE = config.PROJECT_DIR / "data" / "S_extraction.xlsx"


def load_x_row(scenario_folder):
    """Loads system/x.pkl and transposes it into a row (sectors as columns)."""
    x = pd.read_pickle(scenario_folder / "system" / "x.pkl")
    return x.iloc[:, 0]  # Series indexed by (origin, region, category, sub_category, sector)


def build_x_sheet():
    scenario_folders = [BASE_YEAR_FOLDER] + OTHER_SCENARIO_FOLDERS
    rows = [load_x_row(folder) for folder in scenario_folders]
    df = pd.concat(rows, axis=1).T
    df.index = pd.Index([f.name for f in scenario_folders], name="scenario")
    return df


def get_dom_extension_names(scenario_folder):
    """Names of the sub-processes (lp) having a dom_<lp> extension folder."""
    ext_dir = scenario_folder / "extensions"
    return sorted(
        p.name[len("dom_"):]
        for p in ext_dir.iterdir()
        if p.is_dir() and p.name.startswith("dom_")
    )


def sheet_name(prefix, lp_name):
    return f"{prefix}_{lp_name}"[:31]


def main():
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        build_x_sheet().to_excel(writer, sheet_name="x")

        for lp_name in get_dom_extension_names(BASE_YEAR_FOLDER):
            ext_dir = BASE_YEAR_FOLDER / "extensions" / f"dom_{lp_name}"

            f_x_dom_path = ext_dir / "F_x_dom.pkl"
            if f_x_dom_path.exists():
                pd.read_pickle(f_x_dom_path).to_excel(writer, sheet_name=sheet_name("Fx", lp_name))
            else:
                print(f"[info] F_x_dom.pkl missing for {lp_name}, sheet not created.")

            f_y_tot_path = ext_dir / "F_Y_tot.pkl"
            if f_y_tot_path.exists():
                pd.read_pickle(f_y_tot_path).to_excel(writer, sheet_name=sheet_name("FY", lp_name))
            else:
                print(f"[info] F_Y_tot.pkl missing for {lp_name}, sheet not created.")

    print(f"Workbook written: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
