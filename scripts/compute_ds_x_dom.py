"""
Calcule dS, la variation relative de S (= F_x_dom / x) entre chaque scénario 2050
(S1-S4, TEND) et Base_year_2015, pour les extensions manuellement choquées
(dom_land_use, dom_biogeochemical, dom_water), à partir des chocs définis dans
my_manual_param.xlsx.

Pour un row_name et un scénario donnés :
    F_x_dom_2050 = F_x_dom_base_year * (1 + choc)   (choc appliqué à tous les secteurs)
    S_base       = F_x_dom_base_year / x_base_year
    S_2050       = F_x_dom_2050 / x_2050
    dS           = S_2050 / S_base - 1

dS est initialisé à 0 pour tous les indicateurs (même format que les feuilles Fx_*
de S_extraction.xlsx : indicateurs en ligne, secteurs en colonne) ; seules les
lignes dont le row_name figure dans my_manual_param.xlsx ET dont le choc est
renseigné et non nul sont recalculées (un choc à 0 ou vide signifie "pas encore
calibré" et laisse dS=0, sans quoi dS deviendrait le ratio compensatoire qui
annule l'effet volume de x). Les row_name de my_manual_param.xlsx absents de
S_extraction.xlsx sont ignorés.

dS_x_dom (.pkl et .xlsx) est écrit, par scénario et par extension choquée, dans
MatMat/matmat-ademe/.../2-shocks/1-transitions_2050/<scenario>/extensions/dom_<lp>/.

Les chocs "F_Y_tot" du même fichier n'ont pas de dimension sectorielle : ils sont
appliqués directement, en place, dans
Module_PlaneFR/data/3.10.2/<scenario>/extensions/dom_<lp>/F_Y_tot.pkl, en
recalculant à chaque fois new_value = valeur base_year (feuille FY_<lp> de
S_extraction.xlsx) x (1 + choc). Partir de la valeur base_year (et non de la
valeur déjà présente dans le F_Y_tot.pkl du scénario) rend le script idempotent
sans backup : le réexécuter ne cumule jamais le choc, même si le fichier
scénario a été régénéré entre-temps par le modèle amont.
"""

from pathlib import Path

import pandas as pd

MODULE_PLANEFR_DIR = Path(r"C:\Users\Arnaud\Documents\CIRED\PlaneFR\Code\Module_PlaneFR")
MATMAT_DIR = Path(r"C:\Users\Arnaud\Documents\CIRED\PlaneFR\Code\MatMat\matmat-ademe")

S_EXTRACTION_FILE = MODULE_PLANEFR_DIR / "data" / "S_extraction.xlsx"
MANUAL_PARAM_FILE = (
    MATMAT_DIR / "data" / "4-PlaneFR" / "Settings" / "a-manual_shocks" / "input" / "my_manual_param.xlsx"
)
SCENARIO_DATA_DIR = MODULE_PLANEFR_DIR / "data" / "3.10.2"
SHOCKS_OUTPUT_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "2-shocks" / "1-transitions_2050"

BASE_YEAR_NAME = "Base_year_2015"
SCENARIO_FOLDER_NAMES = {
    "S1": "S1_2050",
    "S2": "S2_2050",
    "S3": "S3_2050",
    "S4": "S4_2050",
    "TEND": "TEND_2050",
}
LP_NAMES = ["land_use", "biogeochemical", "water"]  # feuilles présentes dans my_manual_param.xlsx


def load_x_domestic():
    """Feuille 'x' de S_extraction.xlsx, restreinte aux secteurs domestiques
    (mêmes colonnes region/category/sub_category/sector que F_x_dom)."""
    x = pd.read_excel(S_EXTRACTION_FILE, sheet_name="x", header=list(range(5)), index_col=0)
    return x.xs("domestic", axis=1, level="origin")


def load_f_x_dom_base(lp_name):
    return pd.read_excel(S_EXTRACTION_FILE, sheet_name=f"Fx_{lp_name}", header=list(range(4)), index_col=0)


def load_f_y_tot_base(lp_name):
    return pd.read_excel(S_EXTRACTION_FILE, sheet_name=f"FY_{lp_name}", header=list(range(2)), index_col=0)


def load_manual_shocks(lp_name):
    """Reconstruit un tableau propre à partir de my_manual_param.xlsx : la ligne 1
    porte les noms de scénario (S1..TEND), la ligne 3 les noms de champ
    (variable, row_region, row_name, ...), les données commencent ligne 4."""
    raw = pd.read_excel(MANUAL_PARAM_FILE, sheet_name=f"dom_{lp_name}", header=None)
    scenario_cols = raw.iloc[0, 7:].tolist()
    field_cols = raw.iloc[2, 0:7].tolist()
    data = raw.iloc[3:].reset_index(drop=True)
    data.columns = field_cols + scenario_cols
    return data


def compute_ds(lp_name, x_dom):
    f_base = load_f_x_dom_base(lp_name)
    ds_by_scenario = {
        short: pd.DataFrame(0.0, index=f_base.index, columns=f_base.columns) for short in SCENARIO_FOLDER_NAMES
    }

    shocks = load_manual_shocks(lp_name)
    x_shocks = shocks[shocks["variable"] == "F_x_dom"]

    for _, row in x_shocks.iterrows():
        row_name = row["row_name"]
        if row_name not in f_base.index:
            print(f"[skip] {lp_name}: row_name '{row_name}' absent de Fx_{lp_name} (S_extraction.xlsx), ignoré.")
            continue

        f_row_base = f_base.loc[row_name]
        s_base = f_row_base / x_dom.loc[BASE_YEAR_NAME]

        for short, folder_name in SCENARIO_FOLDER_NAMES.items():
            shock = row[short]
            if pd.isna(shock) or shock == 0:
                continue
            f_row_2050 = f_row_base * (1 + shock)
            s_2050 = f_row_2050 / x_dom.loc[folder_name]
            ds_row = (s_2050 / s_base - 1).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
            ds_by_scenario[short].loc[row_name] = ds_row

    return ds_by_scenario


def write_ds_outputs(lp_name, ds_by_scenario):
    for short, folder_name in SCENARIO_FOLDER_NAMES.items():
        ds = ds_by_scenario[short]
        if (ds == 0).all().all():
            continue  # aucun choc F_x_dom pour ce couple scénario/extension

        out_dir = SHOCKS_OUTPUT_DIR / folder_name / "extensions" / f"dom_{lp_name}"
        out_dir.mkdir(parents=True, exist_ok=True)
        if not isinstance(ds.index, pd.MultiIndex):
            ds.index = pd.MultiIndex.from_arrays([ds.index], names=ds.index.names)
        ds.to_pickle(out_dir / "dS_x_dom.pkl")
        ds.to_excel(out_dir / "dS_x_dom.xlsx", sheet_name="dS_x_dom")
        print(f"[write] {out_dir / 'dS_x_dom.xlsx'} (+ .pkl)")


def apply_f_y_tot_shocks(lp_name):
    fy_base = load_f_y_tot_base(lp_name)
    shocks = load_manual_shocks(lp_name)
    y_shocks = shocks[shocks["variable"] == "F_Y_tot"]

    for _, row in y_shocks.iterrows():
        row_name = row["row_name"]
        if row_name not in fy_base.index:
            print(f"[skip] {lp_name}: row_name '{row_name}' absent de FY_{lp_name} (S_extraction.xlsx), ignoré.")
            continue
        base_value = fy_base.loc[row_name]

        for short, folder_name in SCENARIO_FOLDER_NAMES.items():
            shock = row[short]
            if pd.isna(shock) or shock == 0:
                continue

            f_y_path = SCENARIO_DATA_DIR / folder_name / "extensions" / f"dom_{lp_name}" / "F_Y_tot.pkl"
            f_y = pd.read_pickle(f_y_path)
            if row_name not in f_y.index:
                print(f"[skip] {folder_name}/dom_{lp_name}: '{row_name}' absent de F_Y_tot.pkl, ignoré.")
                continue

            f_y.loc[row_name] = base_value * (1 + shock)
            f_y.to_pickle(f_y_path)
            print(f"[update] {f_y_path} : '{row_name}' = base_year x (1{shock:+.4f})")


def main():
    x_dom = load_x_domestic()

    for lp_name in LP_NAMES:
        print(f"=== {lp_name} ===")
        ds_by_scenario = compute_ds(lp_name, x_dom)
        write_ds_outputs(lp_name, ds_by_scenario)
        apply_f_y_tot_shocks(lp_name)


if __name__ == "__main__":
    main()
