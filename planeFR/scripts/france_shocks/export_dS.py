"""
Extracts the data of Base_year_2015 (system/x.pkl + extensions dom_*/F_x_dom.pkl
and dom_*/F_Y_tot.pkl) into an Excel workbook, one sheet per table.

Sheets produced:
- "x": x.pkl of Base_year_2015, transposed (sectors as columns, like F_x_dom),
  with one additional row per 2050 scenario (S1-S4, TEND) for comparison.
  The "scenario" column gives the name of the source folder of each row.
- "Fx_<lp>": F_x_dom.pkl of each dom_* extension of Base_year_2015
  (indicators as rows, sectors as columns; also for ghg_combustion and
  raw_materials, whose F_x_dom is recomputed by sector by reformat_d_cba_k.py).
- "FY_<lp>": F_Y_tot.pkl of each dom_* extension of Base_year_2015, when this
  file exists (missing for ghg_emissions and raw_materials; for
  ghg_combustion, combustion by households written by reformat_d_cba_k.py).
"""

import pandas as pd

from compute_ds_x_dom import BASE_YEAR_NAME, S_EXTRACTION_FILE, SCENARIO_FOLDER_NAMES
from planefr_paths import RAW_2050_DIR

# Engine outputs of the no_SSP group, under the names written by
# the France engine step (planefr.py) and expected by compute_ds_x_dom.py (rows of the "x"
# sheet). The list is explicit, so that other folders placed in no_SSP (e.g.
# copies renamed by hand) are ignored.
NO_SSP_DIR = RAW_2050_DIR / "no_SSP"
BASE_YEAR_FOLDER = NO_SSP_DIR / BASE_YEAR_NAME
OTHER_SCENARIO_FOLDERS = [NO_SSP_DIR / name for name in SCENARIO_FOLDER_NAMES.values()]

OUTPUT_FILE = S_EXTRACTION_FILE


def check_folders():
    missing = [f for f in [BASE_YEAR_FOLDER] + OTHER_SCENARIO_FOLDERS if not (f / "system" / "x.pkl").is_file()]
    if missing:
        raise FileNotFoundError(
            "Engine outputs missing (run planefr.py step engine_no_ssp first): "
            + ", ".join(str(f) for f in missing)
        )


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
    check_folders()
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
