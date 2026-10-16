"""
Extrait, pour chaque scénario IMAGE de data/SSP/Scenarios, les facteurs F, x et S
2050/2020 par région, et les écrit dans Matching_extensions_EXIOBASE_IMAGE.xlsx,
une feuille par scénario (feuille effacée puis recréée si elle existe déjà).

Pour chaque ligne de la feuille "Matching" :
- F 2050/2020 : ratio de la variable "Numérateur F" (somme si "A + B") ;
  lue dans Nutrients.xlsx (scénario "PB_<scénario>") pour le domaine Nutrients,
  dans le csv du scénario sinon (ou dans Nutrients.xlsx si la variable n'existe
  que là, ex. iNH3_volatization_* du domaine Air_emissions).
  Si la cellule est de la forme "A / B + C" (ex. P - agriculture - soil/water) et que
  F est négatif en 2020 ou en 2050 pour une région, l'indicateur après le "/" est
  utilisé à la place de A pour cette région.
- x 2050/2020 : ratio de la variable "Dénominateur x" (csv du scénario).
- S 2050/2020 : F/x ; 1/F si le numérateur est de la forme "1 / <variable>"
  (rendements) ; 1 si F ou x n'est pas calculable.
- Si un rendement "Yield|..." manque dans le scénario (ex. Yield|Oilcrops dans SSP1),
  la ligne reprend les variables F et x de la ligne "Cropland".

Les régions IMAGE sont agrégées selon la colonne "Code agrégé" de la feuille
"Régions" (somme des valeurs 2020 et 2050 avant calcul des ratios).
"""

import re
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font

MODULE_PLANEFR_DIR = Path(r"C:\Users\Arnaud\Documents\CIRED\PlaneFR\Code\Module_PlaneFR")

sys.path.insert(0, str(MODULE_PLANEFR_DIR / "notebooks"))
from planefr_lib import config  # noqa: E402

SSP_DIR = config.DATA_DIR / "SSP"
SCENARIOS_DIR = SSP_DIR / "Scenarios"
NUTRIENTS_FILE = SSP_DIR / "Nutrients.xlsx"
MATCHING_FILE = SSP_DIR / "Matching_extensions_EXIOBASE_IMAGE.xlsx"

MATCHING_SHEET = "Matching"
REGIONS_SHEET = "Régions"
NUTRIENTS_DOMAIN = "Nutrients"
YIELD_FALLBACK_EXTENSION = "Cropland"

LABEL_COLUMNS = ["Domaine", "Extension EXIOBASE", "Secteurs EXIOBASE"]

YEAR_BASE, YEAR_TARGET = 2020, 2050
VALUE_COLUMNS = ["F 2050/2020", "x 2050/2020", "S 2050/2020"]


def parse_variables(cell, alternative=False):
    """Analyse une cellule "Numérateur F" / "Dénominateur x".

    Renvoie (liste de variables IMAGE, inverse) ; liste vide si pas de variable.
    Ex. "A + B (Mt MS/an)" -> (["A", "B"], False) ; "1 / Yield|Cereal (t/ha)" -> (["Yield|Cereal"], True).
    Une cellule "A (unité) / B + C" a un indicateur de repli après le "/" :
    alternative=False renvoie A, alternative=True renvoie B + C (liste vide si absent).
    """
    if pd.isna(cell):
        return [], False
    text = str(cell).strip()
    inverse = text.startswith("1 /")
    if inverse:
        text = text[len("1 /"):].strip()
    primary, _, fallback = text.partition(" / ")
    text = fallback if alternative else primary
    text = re.sub(r"\s*\([^()]*\)\s*$", "", text.strip())  # retire l'unité finale
    if text in ("", "–", "-"):
        return [], inverse
    return [v.strip() for v in text.split(" + ")], inverse


def load_matching():
    df = pd.read_excel(MATCHING_FILE, sheet_name=MATCHING_SHEET)
    return df.rename(columns={
        df.columns[0]: "Domaine",
        df.columns[1]: "Extension EXIOBASE",
        df.columns[2]: "Secteurs EXIOBASE",
        df.columns[3]: "Numérateur F",
        df.columns[4]: "Dénominateur x",
    })


def load_region_maps():
    """Dictionnaires code IMAGE (csv) -> code agrégé et code IMAGE-GNM -> code agrégé."""
    df = pd.read_excel(MATCHING_FILE, sheet_name=REGIONS_SHEET).dropna(subset=["Code agrégé"])
    gnm_col, image_col, agg_col = df.columns[0], df.columns[1], "Code agrégé"
    image_map = dict(zip(df[image_col], df[agg_col]))
    gnm_map = dict(zip(df[gnm_col], df[agg_col]))
    region_order = list(dict.fromkeys(df[agg_col]))
    return image_map, gnm_map, region_order


def aggregate(df, region_map):
    """Tableau (variable x région agrégée) des valeurs 2020 et 2050, sommées par région agrégée."""
    df = df.assign(Region=df["Region"].map(region_map)).dropna(subset=["Region"])
    return df.groupby(["Variable", "Region"])[[YEAR_BASE, YEAR_TARGET]].sum(min_count=1)


def load_scenario(csv_path, image_map):
    df = pd.read_csv(csv_path, encoding="latin-1")
    df = df.rename(columns={str(YEAR_BASE): YEAR_BASE, str(YEAR_TARGET): YEAR_TARGET})
    return aggregate(df, image_map)


def load_nutrients(scenario_name, gnm_map):
    df = pd.read_excel(NUTRIENTS_FILE, header=1)
    df = df[df["Scenario"] == f"PB_{scenario_name}"]
    if df.empty:
        print(f"[info] Scénario PB_{scenario_name} absent de Nutrients.xlsx.")
    return aggregate(df, gnm_map)


def ratio(data, variables, region):
    """Ratio 2050/2020 de la somme des variables pour une région (NaN si non calculable)."""
    if not variables:
        return np.nan
    try:
        values = data.loc[[(v, region) for v in variables]]
    except KeyError:
        return np.nan
    base, target = values[YEAR_BASE].sum(min_count=len(variables)), values[YEAR_TARGET].sum(min_count=len(variables))
    if pd.isna(base) or pd.isna(target) or base == 0:
        return np.nan
    return target / base


def has_variables(data, variables):
    known = data.index.get_level_values("Variable")
    return all(v in known for v in variables)


def f_source(row, f_vars, scenario_data, nutrients_data):
    """Nutrients.xlsx pour le domaine Nutrients, ou si les variables n'existent que là (ex. iNH3_*)."""
    if row["Domaine"] == NUTRIENTS_DOMAIN:
        return nutrients_data
    if not has_variables(scenario_data, f_vars) and has_variables(nutrients_data, f_vars):
        return nutrients_data
    return scenario_data


def has_negative(data, variables, region):
    """True si la somme des variables est négative en 2020 ou en 2050 pour la région."""
    try:
        values = data.loc[[(v, region) for v in variables]]
    except KeyError:
        return False
    return bool((values[[YEAR_BASE, YEAR_TARGET]].sum() < 0).any())


def compute_row(row, scenario_data, nutrients_data, region):
    f_vars, inverse = parse_variables(row["Numérateur F"])
    alt_vars, _ = parse_variables(row["Numérateur F"], alternative=True)
    x_vars, _ = parse_variables(row["Dénominateur x"])
    source = f_source(row, f_vars, scenario_data, nutrients_data)
    if alt_vars and has_negative(source, f_vars, region):
        f_vars = alt_vars  # F négatif (2020 ou 2050) : indicateur de repli
    f = ratio(source, f_vars, region)
    x = ratio(scenario_data, x_vars, region)
    if inverse:
        s = 1 / f if pd.notna(f) and f != 0 else 1.0
    elif pd.notna(f) and pd.notna(x) and x != 0:
        s = f / x
    else:
        s = 1.0
    return f, x, s


def apply_yield_fallback(matching, scenario_data, scenario_name):
    """Lignes "1 / Yield|..." dont le rendement manque : reprend F et x de la ligne Cropland."""
    cropland = matching.loc[matching["Extension EXIOBASE"] == YIELD_FALLBACK_EXTENSION].iloc[0]
    matching = matching.copy()
    for i, row in matching.iterrows():
        f_vars, inverse = parse_variables(row["Numérateur F"])
        if inverse and not has_variables(scenario_data, f_vars):
            matching.loc[i, ["Numérateur F", "Dénominateur x"]] = cropland[["Numérateur F", "Dénominateur x"]].values
            print(f"[info] {scenario_name} : {', '.join(f_vars)} absent, "
                  f"'{row['Extension EXIOBASE']}' reprend la ligne '{YIELD_FALLBACK_EXTENSION}'.")
    return matching


def check_variables(matching, scenario_data, nutrients_data, scenario_name):
    """Signale les variables de la feuille Matching introuvables dans les données."""
    for _, row in matching.iterrows():
        f_vars, _ = parse_variables(row["Numérateur F"])
        alt_vars, _ = parse_variables(row["Numérateur F"], alternative=True)
        x_vars, _ = parse_variables(row["Dénominateur x"])
        f_src = f_source(row, f_vars, scenario_data, nutrients_data)
        for vars_, source in [(f_vars, f_src), (alt_vars, f_src), (x_vars, scenario_data)]:
            for v in vars_:
                if not has_variables(source, [v]):
                    print(f"[info] {scenario_name} : variable '{v}' introuvable ({row['Extension EXIOBASE']}).")


def write_sheet(wb, sheet_name, matching, results, region_order):
    """(Re)crée la feuille : 2 lignes d'en-tête (code région / F, x, S), puis une ligne par extension."""
    if sheet_name in wb.sheetnames:
        index = wb.sheetnames.index(sheet_name)
        wb.remove(wb[sheet_name])
        ws = wb.create_sheet(sheet_name, index)
    else:
        ws = wb.create_sheet(sheet_name)

    bold, center = Font(bold=True), Alignment(horizontal="center", vertical="center")
    n_labels = len(LABEL_COLUMNS)
    for col, label in enumerate(LABEL_COLUMNS, start=1):
        ws.cell(row=1, column=col, value=label).font = bold
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
    for i, region in enumerate(region_order):
        first_col = n_labels + 1 + i * len(VALUE_COLUMNS)
        ws.cell(row=1, column=first_col, value=region)
        ws.merge_cells(start_row=1, start_column=first_col, end_row=1, end_column=first_col + len(VALUE_COLUMNS) - 1)
        for j, label in enumerate(VALUE_COLUMNS):
            ws.cell(row=2, column=first_col + j, value=label)
    for cells in ws.iter_rows(min_row=1, max_row=2):
        for cell in cells:
            cell.font, cell.alignment = bold, center

    for r, (_, row) in enumerate(matching.iterrows(), start=3):
        for col, label in enumerate(LABEL_COLUMNS, start=1):
            ws.cell(row=r, column=col, value=row[label])
        for i, region in enumerate(region_order):
            for j, value in enumerate(results[(r - 3, region)]):
                ws.cell(row=r, column=n_labels + 1 + i * len(VALUE_COLUMNS) + j,
                        value=None if pd.isna(value) else float(value))

    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 60
    ws.freeze_panes = "D3"


def main():
    matching = load_matching().dropna(subset=["Extension EXIOBASE"]).reset_index(drop=True)
    image_map, gnm_map, region_order = load_region_maps()
    wb = openpyxl.load_workbook(MATCHING_FILE)

    for csv_path in sorted(SCENARIOS_DIR.glob("*.csv")):
        scenario_name = csv_path.stem
        scenario_data = load_scenario(csv_path, image_map)
        nutrients_data = load_nutrients(scenario_name, gnm_map)
        scenario_matching = apply_yield_fallback(matching, scenario_data, scenario_name)
        check_variables(scenario_matching, scenario_data, nutrients_data, scenario_name)
        results = {
            (i, region): compute_row(row, scenario_data, nutrients_data, region)
            for i, row in scenario_matching.iterrows()
            for region in region_order
        }
        write_sheet(wb, scenario_name[:31], matching, results, region_order)
        print(f"Feuille '{scenario_name}' écrite.")

    try:
        wb.save(MATCHING_FILE)
    except PermissionError:
        sys.exit(f"Impossible d'écrire {MATCHING_FILE} : fermer le fichier dans Excel puis relancer.")
    print(f"Classeur écrit : {MATCHING_FILE}")


if __name__ == "__main__":
    main()
