"""
Extrait, pour chaque scénario IMAGE de data/SSP/Scenarios, les facteurs F, x et S
2050/2020 par région, et les écrit dans Matching_extensions_EXIOBASE_IMAGE.xlsx,
une feuille par scénario (feuille effacée puis recréée si elle existe déjà).

Pour chaque ligne de la feuille "Matching" :
- F 2050/2020 : ratio 2050/2020 de la formule "Numérateur F", évaluée séparément
  en 2020 et en 2050. La formule combine des variables IMAGE avec les opérateurs
  "+", "-" (ou "−"), "x", "/", des nombres et des parenthèses ; les parenthèses
  placées après une variable sont des unités et sont ignorées, ex.
  "iNH3_volatization_arable (kgN/an) x (1 − Land Cover|Cropland|Energy Crops / Land Cover|Cropland)".
  "A OU B" (priorité la plus faible) vaut A, sauf si A est négatif en 2020 ou en
  2050 pour la région, auquel cas B est utilisé (ex. P - agriculture - soil/water).
  Chaque variable est lue dans Nutrients.xlsx (scénario "PB_<scénario>") pour le
  domaine Nutrients, dans le csv du scénario sinon ; si elle est absente de cette
  source, elle est lue dans l'autre (ex. iNH3_volatization_* du domaine
  Air_emissions, Land Cover|* dans les lignes du domaine Nutrients).
- x 2050/2020 : ratio de la formule "Dénominateur x" (csv du scénario).
- S 2050/2020 : F/x ; 1/F si le numérateur est de la forme "1 / <formule>"
  (rendements, F est alors le ratio de <formule>) ; 1 si F ou x n'est pas calculable.
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

# Opérateurs des formules (entourés d'espaces dans les cellules), par priorité croissante.
OPERATOR_SYMBOLS = {"OU": "OU", "+": "+", "-": "-", "−": "-", "x": "*", "×": "*", "*": "*", "/": "/"}
OPERATOR_PATTERN = "|".join(re.escape(op) for op in OPERATOR_SYMBOLS)
PRECEDENCE = [("OU",), ("+", "-"), ("*", "/")]
ARITHMETIC = {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide}
EMPTY_CELLS = ("", "–", "-")


def strip_units(text):
    """Retire les parenthèses d'unité placées après une variable, ex. "A (kgN/an) x (1 − B)" -> "A x (1 − B)".

    Une parenthèse est un regroupement si elle contient un opérateur ou suit un opérateur,
    une autre parenthèse ouvrante ou le début de la cellule.
    """
    def replace(match):
        prefix = text[:match.start()].rstrip()
        is_group = (re.search(rf"\s({OPERATOR_PATTERN})\s", match.group(1))
                    or not prefix or prefix.endswith("(")
                    or re.search(rf"(^|\s)({OPERATOR_PATTERN})$", prefix))
        return match.group(0) if is_group else ""
    return re.sub(r"\s*\(([^()]*)\)", replace, text)


def tokenize(text):
    """Jetons ("name", texte), ("op", symbole) ou ("paren", "(" / ")")."""
    tokens = []
    for i, part in enumerate(re.split(rf"\s+({OPERATOR_PATTERN})\s+|([()])", text)):
        if part is None or not part.strip():
            continue
        kind = ("name", "op", "paren")[i % 3]
        tokens.append((kind, OPERATOR_SYMBOLS[part] if kind == "op" else part.strip()))
    return tokens


def parse_expression(tokens, pos=0, level=0):
    """Analyse descendante : renvoie (arbre, position suivante).

    Arbre : ("var", nom), ("num", valeur) ou (opérateur, gauche, droite).
    """
    if level == len(PRECEDENCE):
        return parse_atom(tokens, pos)
    left, pos = parse_expression(tokens, pos, level + 1)
    while pos < len(tokens) and tokens[pos][0] == "op" and tokens[pos][1] in PRECEDENCE[level]:
        right, next_pos = parse_expression(tokens, pos + 1, level + 1)
        left, pos = (tokens[pos][1], left, right), next_pos
    return left, pos


def parse_atom(tokens, pos):
    if pos >= len(tokens):
        raise ValueError("formule incomplète")
    kind, value = tokens[pos]
    if (kind, value) == ("paren", "("):
        node, pos = parse_expression(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ("paren", ")"):
            raise ValueError("parenthèse non fermée")
        return node, pos + 1
    if kind == "name":
        try:
            return ("num", float(value)), pos + 1
        except ValueError:
            return ("var", value), pos + 1
    raise ValueError(f"jeton inattendu '{value}'")


def parse_formula(cell):
    """Analyse une cellule "Numérateur F" / "Dénominateur x".

    Renvoie (arbre, inverse) ; arbre None si pas de variable.
    Ex. "A + B (Mt MS/an)" -> (("+", A, B), False) ; "1 / Yield|Cereal (t/ha)" -> (("var", "Yield|Cereal"), True).
    """
    if pd.isna(cell):
        return None, False
    text = strip_units(str(cell).strip()).strip()
    if text in EMPTY_CELLS:
        return None, False
    tokens = tokenize(text)
    try:
        tree, pos = parse_expression(tokens)
        if pos != len(tokens):
            raise ValueError(f"jeton inattendu '{tokens[pos][1]}'")
    except ValueError as error:
        raise ValueError(f"Formule invalide ({error}) : {cell!r}") from None
    if tree[0] == "/" and tree[1] == ("num", 1.0):
        return tree[2], True
    return tree, False


def formula_variables(tree):
    """Variables IMAGE de la formule, dans l'ordre d'apparition."""
    if tree is None or tree[0] == "num":
        return []
    if tree[0] == "var":
        return [tree[1]]
    return list(dict.fromkeys(formula_variables(tree[1]) + formula_variables(tree[2])))


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


def has_variables(data, variables):
    known = data.index.get_level_values("Variable")
    return all(v in known for v in variables)


def f_sources(row, scenario_data, nutrients_data):
    """Sources des variables de F, par ordre de préférence : Nutrients.xlsx d'abord pour le domaine Nutrients."""
    if row["Domaine"] == NUTRIENTS_DOMAIN:
        return [nutrients_data, scenario_data]
    return [scenario_data, nutrients_data]


def lookup_values(sources, variable, region):
    """Valeurs [2020, 2050] de la variable dans la première source qui la contient (NaN sinon)."""
    for data in sources:
        try:
            return data.loc[(variable, region), [YEAR_BASE, YEAR_TARGET]].to_numpy(dtype=float)
        except KeyError:
            continue
    return np.full(2, np.nan)


def evaluate(tree, sources, region):
    """Valeurs [2020, 2050] de la formule pour une région (NaN si non calculable)."""
    kind = tree[0]
    if kind == "num":
        return np.full(2, tree[1])
    if kind == "var":
        return lookup_values(sources, tree[1], region)
    left = evaluate(tree[1], sources, region)
    if kind == "OU":
        # A négatif (2020 ou 2050) : indicateur de repli B
        return evaluate(tree[2], sources, region) if (left < 0).any() else left
    with np.errstate(divide="ignore", invalid="ignore"):
        result = ARITHMETIC[kind](left, evaluate(tree[2], sources, region))
    return np.where(np.isfinite(result), result, np.nan)


def ratio(tree, sources, region):
    """Ratio 2050/2020 de la formule pour une région (NaN si non calculable)."""
    if tree is None:
        return np.nan
    base, target = evaluate(tree, sources, region)
    if pd.isna(base) or pd.isna(target) or base == 0:
        return np.nan
    return target / base


def compute_row(row, scenario_data, nutrients_data, region):
    f_tree, inverse = parse_formula(row["Numérateur F"])
    x_tree, _ = parse_formula(row["Dénominateur x"])
    f = ratio(f_tree, f_sources(row, scenario_data, nutrients_data), region)
    x = ratio(x_tree, [scenario_data], region)
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
        f_tree, inverse = parse_formula(row["Numérateur F"])
        f_vars = formula_variables(f_tree)
        if inverse and not has_variables(scenario_data, f_vars):
            matching.loc[i, ["Numérateur F", "Dénominateur x"]] = cropland[["Numérateur F", "Dénominateur x"]].values
            print(f"[info] {scenario_name} : {', '.join(f_vars)} absent, "
                  f"'{row['Extension EXIOBASE']}' reprend la ligne '{YIELD_FALLBACK_EXTENSION}'.")
    return matching


def check_variables(matching, scenario_data, nutrients_data, scenario_name):
    """Signale les variables de la feuille Matching introuvables dans les données."""
    for _, row in matching.iterrows():
        f_tree, _ = parse_formula(row["Numérateur F"])
        x_tree, _ = parse_formula(row["Dénominateur x"])
        for tree, sources in [(f_tree, f_sources(row, scenario_data, nutrients_data)), (x_tree, [scenario_data])]:
            for v in formula_variables(tree):
                if not any(has_variables(source, [v]) for source in sources):
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
