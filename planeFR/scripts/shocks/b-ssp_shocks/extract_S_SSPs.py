"""
Extracts, for each IMAGE scenario of data/SSP/Scenarios, the F, x and S
2050/2020 factors by region, and writes them into Matching_extensions_EXIOBASE_IMAGE.xlsx,
one sheet per scenario (sheet deleted then recreated if it already exists).

For each row of the "Matching" sheet:
- F 2050/2020: 2050/2020 ratio of the "F (IMAGE)" formula, evaluated separately
  in 2020 and in 2050. The formula combines IMAGE variables with the operators
  "+", "-" (or "−"), "x", "/", numbers and parentheses; the parentheses placed
  after a variable are units and are ignored, e.g.
  "iNH3_volatization_arable (kgN/an) x (1 − Land Cover|Cropland|Energy Crops / Land Cover|Cropland)".
  "max (A, B)" / "min (A, B)" apply year by year (e.g. floor at 0).
  "A OU B" / "A OR B" (lowest precedence) is A, unless A is negative in 2020 or
  in 2050 for the region, in which case B is used (e.g. P - agriculture - soil/water).
  Each variable is read in Nutrients.xlsx (scenario "PB_<scenario>") for the
  Nutrients group, in the csv of the scenario otherwise; if it is missing from
  this source, it is read in the other one (e.g. iNH3_volatization_* of the
  Air_emissions group, Land Cover|* in the rows of the Nutrients group).
- x 2050/2020: ratio of the "x (IMAGE)" formula (csv of the scenario).
- S 2050/2020: F/x; if the numerator has the form "1 / <formula>" (yields),
  F is the ratio of 1 / <formula>, i.e. S; 1 if F or x cannot be computed.
  S is also 1 when the 2020 intensity of the region (F/x) is negligible compared
  with that of the World (less than MIN_RELATIVE_INTENSITY times): the 2050/2020
  ratio of an almost-zero 2020 value makes no sense (e.g. coal in Indonesian
  services, F 2020 ~ 1e-26 x World -> S ~ 1e15), and these factors, applied to
  the coefficients of A by generate_shock_dS.py, make the Leontief matrix unusable.
- If a "Yield|..." yield is missing from the scenario (e.g. Yield|Oilcrops in
  SSP1), the row takes the F and x variables of the "Cropland" row.

Common baseline: the 2020 values of all the variables (csv and Nutrients.xlsx)
are those of the BASELINE_SCENARIO scenario (SSP2); only the 2050 values are
specific to each scenario. A variable missing from SSP2 keeps its 2020 value.

The IMAGE regions are aggregated according to the "Code aggregated" column of
the "Regions" sheet (sum of the 2020 and 2050 values before computing the
ratios). Missing or zero World values are replaced by the sum of the regions.

The World S of each scenario is also written into the Matching sheet, column
"S 2050/2020 (World <scenario>)" (regenerated at each run), as well as the World
F and x of the reference scenario, columns "F 2050/2020 (World SSP2)" and
"x 2050/2020 (World SSP2)".
"""

import re
import sys
from copy import copy
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font
from openpyxl.utils import column_index_from_string, get_column_letter

# Shared modules of planeFR/scripts/_common
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
from planefr_paths import MODULE_PLANEFR_DIR  # noqa: E402

sys.path.insert(0, str(MODULE_PLANEFR_DIR / "notebooks"))
from planefr_lib import config  # noqa: E402

SSP_DIR = config.DATA_DIR / "SSP"
SCENARIOS_DIR = SSP_DIR / "Scenarios"
NUTRIENTS_FILE = SSP_DIR / "Nutrients.xlsx"
MATCHING_FILE = SSP_DIR / "Matching_extensions_EXIOBASE_IMAGE.xlsx"

MATCHING_SHEET = "Matching"
REGIONS_SHEET = "Regions"
REGIONS_AGGREGATED_COLUMN = "Code aggregated"
NUTRIENTS_GROUP = "Nutrients"
YIELD_FALLBACK_STRESSOR = "Cropland"

# Columns of the Matching sheet (renamed by position in load_matching, so that a
# change of spelling/spacing in the file headers does not break the script).
GROUP_COLUMN = "EXIOBASE groups"
STRESSOR_COLUMN = "EXIOBASE stressors"
PRODUCTS_COLUMN = "EXIOBASE products"
F_FORMULA_COLUMN = "F (IMAGE)"
X_FORMULA_COLUMN = "x (IMAGE)"
# Label columns copied at the start of each scenario sheet
LABEL_COLUMNS = [GROUP_COLUMN, STRESSOR_COLUMN, PRODUCTS_COLUMN]

YEAR_BASE, YEAR_TARGET = 2020, 2050
BASELINE_SCENARIO = "SSP2"  # provides the 2020 values (F and x) of all the scenarios
VALUE_COLUMNS = ["F 2050/2020", "x 2050/2020", "S 2050/2020"]
# 2020 intensity (F/x) of the region, relative to that of the World, below which S is 1
MIN_RELATIVE_INTENSITY = 1e-2

# "S 2050/2020 (World <scenario>)" columns of the Matching sheet
WORLD_REGION, WORLD_LABEL = "World", "World"
WORLD_S_HEADER = "S 2050/2020"
# World F and x columns of the reference scenario in the Matching sheet (index in the results)
WORLD_BASELINE_COLUMNS = {f"F 2050/2020 ({WORLD_LABEL} {BASELINE_SCENARIO})": 0,
                          f"x 2050/2020 ({WORLD_LABEL} {BASELINE_SCENARIO})": 1}

# Formula operators (surrounded by spaces in the cells), by increasing precedence.
# "OU" (French "or", still used in the Matching file) and "OR" are equivalent.
OPERATOR_SYMBOLS = {"OU": "OR", "OR": "OR", "+": "+", "-": "-", "−": "-", "x": "*", "×": "*", "*": "*", "/": "/"}
OPERATOR_PATTERN = "|".join(re.escape(op) for op in OPERATOR_SYMBOLS)
PRECEDENCE = [("OR",), ("+", "-"), ("*", "/")]
ARITHMETIC = {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide}
# Two-argument functions separated by a comma (with or without space; a comma
# between two digits is a decimal comma), applied year by year, e.g. "max (A, 0)".
FUNCTIONS = {"max": np.maximum, "min": np.minimum}
EMPTY_CELLS = ("", "–", "-")


def strip_units(text):
    """Remove the unit parentheses placed after a variable, e.g. "A (kgN/an) x (1 − B)" -> "A x (1 − B)".

    A parenthesis is a grouping if it contains an operator or follows an
    operator, another opening parenthesis, a function name or the start of the cell.
    """
    def replace(match):
        prefix = text[:match.start()].rstrip()
        is_group = (re.search(rf"\s({OPERATOR_PATTERN})\s", match.group(1))
                    or not prefix or prefix.endswith("(")
                    or re.search(rf"(^|\s)({OPERATOR_PATTERN})$", prefix)
                    or re.search(rf"(^|[\s(])({'|'.join(FUNCTIONS)})$", prefix))
        return match.group(0) if is_group else ""
    return re.sub(r"\s*\(([^()]*)\)", replace, text)


def tokenize(text):
    """Tokens ("name", text), ("op", symbol) or ("paren", "(" / ")" / ",")."""
    tokens = []
    for i, part in enumerate(re.split(rf"\s+({OPERATOR_PATTERN})\s+|([()]|,(?!\d)|(?<!\d),)", text)):
        if part is None or not part.strip():
            continue
        kind = ("name", "op", "paren")[i % 3]
        tokens.append((kind, OPERATOR_SYMBOLS[part] if kind == "op" else part.strip()))
    return tokens


def parse_expression(tokens, pos=0, level=0):
    """Recursive descent parsing: returns (tree, next position).

    Tree: ("var", name), ("num", value) or (operator or function, left, right).
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
        raise ValueError("incomplete formula")
    kind, value = tokens[pos]
    if (kind, value) == ("paren", "("):
        node, pos = parse_expression(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ("paren", ")"):
            raise ValueError("unclosed parenthesis")
        return node, pos + 1
    if kind == "name" and value in FUNCTIONS and tokens[pos + 1:pos + 2] == [("paren", "(")]:
        first, pos = parse_expression(tokens, pos + 2)
        if tokens[pos:pos + 1] != [("paren", ",")]:
            raise ValueError(f"{value} expects two arguments")
        second, pos = parse_expression(tokens, pos + 1)
        if tokens[pos:pos + 1] != [("paren", ")")]:
            raise ValueError("unclosed parenthesis")
        return (value, first, second), pos + 1
    if kind == "name":
        try:
            return ("num", float(value.replace(",", "."))), pos + 1  # decimal comma "0,1"
        except ValueError:
            return ("var", value), pos + 1
    raise ValueError(f"unexpected token '{value}'")


def parse_formula(cell):
    """Parse an "F (IMAGE)" / "x (IMAGE)" cell.

    Returns (tree, inverse); tree None if there is no variable.
    E.g. "A + B (Mt MS/an)" -> (("+", A, B), False); "1 / Yield|Cereal (t/ha)" -> (("var", "Yield|Cereal"), True).
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
            raise ValueError(f"unexpected token '{tokens[pos][1]}'")
    except ValueError as error:
        raise ValueError(f"Invalid formula ({error}): {cell!r}") from None
    if tree[0] == "/" and tree[1] == ("num", 1.0):
        return tree[2], True
    return tree, False


def formula_variables(tree):
    """IMAGE variables of the formula, in order of appearance."""
    if tree is None or tree[0] == "num":
        return []
    if tree[0] == "var":
        return [tree[1]]
    return list(dict.fromkeys(formula_variables(tree[1]) + formula_variables(tree[2])))


def load_matching():
    df = pd.read_excel(MATCHING_FILE, sheet_name=MATCHING_SHEET)
    return df.rename(columns={
        df.columns[0]: GROUP_COLUMN,
        df.columns[1]: STRESSOR_COLUMN,
        df.columns[2]: PRODUCTS_COLUMN,
        df.columns[3]: F_FORMULA_COLUMN,
        df.columns[4]: X_FORMULA_COLUMN,
    })


def load_region_maps():
    """Dictionaries IMAGE code (csv) -> aggregated code and IMAGE-GNM code -> aggregated code."""
    df = pd.read_excel(MATCHING_FILE, sheet_name=REGIONS_SHEET).dropna(subset=[REGIONS_AGGREGATED_COLUMN])
    gnm_col, image_col, agg_col = df.columns[0], df.columns[1], REGIONS_AGGREGATED_COLUMN
    image_map = dict(zip(df[image_col], df[agg_col]))
    gnm_map = dict(zip(df[gnm_col], df[agg_col]))
    region_order = list(dict.fromkeys(df[agg_col]))
    return image_map, gnm_map, region_order


def aggregate(df, region_map):
    """Table (variable x aggregated region) of the 2020 and 2050 values, summed by aggregated region."""
    df = df.assign(Region=df["Region"].map(region_map)).dropna(subset=["Region"])
    return with_world_fallback(df.groupby(["Variable", "Region"])[[YEAR_BASE, YEAR_TARGET]].sum(min_count=1))


def with_world_fallback(data):
    """Missing or zero World values replaced by the sum of the other regions.

    The csv does not always fill in World (e.g. Production|Pulp and Paper|Volume = 0,
    Secondary Energy|Heat missing) whereas the regions are filled in.
    """
    is_world = data.index.get_level_values("Region") == WORLD_REGION
    world = data[is_world].droplevel("Region")
    region_sum = data[~is_world].groupby(level="Variable").sum(min_count=1)
    world = world.reindex(world.index.union(region_sum.index))
    world = world.mask(world == 0).combine_first(region_sum).combine_first(world)
    world.index = pd.MultiIndex.from_product([world.index, [WORLD_REGION]], names=["Variable", "Region"])
    return pd.concat([data[~is_world], world]).sort_index()


def load_scenario(csv_path, image_map):
    df = pd.read_csv(csv_path, encoding="latin-1")
    df = df.rename(columns={str(YEAR_BASE): YEAR_BASE, str(YEAR_TARGET): YEAR_TARGET})
    return aggregate(df, image_map)


def load_nutrients(scenario_name, gnm_map):
    df = pd.read_excel(NUTRIENTS_FILE, header=1)
    df = df[df["Scenario"] == f"PB_{scenario_name}"]
    if df.empty:
        print(f"[info] Scenario PB_{scenario_name} missing from Nutrients.xlsx.")
    return aggregate(df, gnm_map)


def with_common_baseline(data, baseline):
    """Copy of data whose 2020 values are those of the reference scenario (if available)."""
    data = data.copy()
    data[YEAR_BASE] = baseline[YEAR_BASE].reindex(data.index).combine_first(data[YEAR_BASE])
    return data


def has_variables(data, variables):
    known = data.index.get_level_values("Variable")
    return all(v in known for v in variables)


def f_sources(row, scenario_data, nutrients_data):
    """Sources of the F variables, by order of preference: Nutrients.xlsx first for the Nutrients group."""
    if row[GROUP_COLUMN] == NUTRIENTS_GROUP:
        return [nutrients_data, scenario_data]
    return [scenario_data, nutrients_data]


def lookup_values(sources, variable, region):
    """[2020, 2050] values of the variable in the first source containing it (NaN otherwise)."""
    for data in sources:
        try:
            return data.loc[(variable, region), [YEAR_BASE, YEAR_TARGET]].to_numpy(dtype=float)
        except KeyError:
            continue
    return np.full(2, np.nan)


def evaluate(tree, sources, region):
    """[2020, 2050] values of the formula for a region (NaN if it cannot be computed)."""
    kind = tree[0]
    if kind == "num":
        return np.full(2, tree[1])
    if kind == "var":
        return lookup_values(sources, tree[1], region)
    left = evaluate(tree[1], sources, region)
    if kind == "OR":
        # A negative (2020 or 2050): fallback indicator B
        return evaluate(tree[2], sources, region) if (left < 0).any() else left
    with np.errstate(divide="ignore", invalid="ignore"):
        result = {**ARITHMETIC, **FUNCTIONS}[kind](left, evaluate(tree[2], sources, region))
    return np.where(np.isfinite(result), result, np.nan)


def ratio(tree, sources, region):
    """2050/2020 ratio of the formula for a region (NaN if it cannot be computed)."""
    if tree is None:
        return np.nan
    base, target = evaluate(tree, sources, region)
    if pd.isna(base) or pd.isna(target) or base == 0:
        return np.nan
    return target / base


def relative_intensity(f_tree, f_src, x_tree, x_src, region):
    """2020 intensity F/x of the region relative to that of the World (NaN if it cannot be computed)."""
    if f_tree is None or x_tree is None or region == WORLD_REGION:
        return np.nan
    f_region, f_world = evaluate(f_tree, f_src, region)[0], evaluate(f_tree, f_src, WORLD_REGION)[0]
    x_region, x_world = evaluate(x_tree, x_src, region)[0], evaluate(x_tree, x_src, WORLD_REGION)[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = abs((f_region / f_world) / (x_region / x_world))
    return rel if np.isfinite(rel) else np.nan


def compute_row(row, scenario_data, nutrients_data, region):
    """(F, x, S, negligible); negligible = S forced to 1 because the 2020 intensity
    of the region is negligible (see MIN_RELATIVE_INTENSITY)."""
    f_tree, inverse = parse_formula(row[F_FORMULA_COLUMN])
    x_tree, _ = parse_formula(row[X_FORMULA_COLUMN])
    f_src = f_sources(row, scenario_data, nutrients_data)
    f = ratio(f_tree, f_src, region)
    x = ratio(x_tree, [scenario_data], region)
    if inverse:
        # F = ratio of "1 / <formula>" (= S), consistent with the displayed numerator
        s = 1 / f if pd.notna(f) and f != 0 else 1.0
        return (s if pd.notna(f) and f != 0 else f), x, s, False
    if pd.isna(f) or pd.isna(x) or x == 0:
        return f, x, 1.0, False
    if relative_intensity(f_tree, f_src, x_tree, [scenario_data], region) < MIN_RELATIVE_INTENSITY:
        return f, x, 1.0, True
    return f, x, f / x, False


def apply_yield_fallback(matching, scenario_data, scenario_name):
    """"1 / Yield|..." rows whose yield is missing: take F and x of the Cropland row."""
    cropland = matching.loc[matching[STRESSOR_COLUMN] == YIELD_FALLBACK_STRESSOR].iloc[0]
    matching = matching.copy()
    for i, row in matching.iterrows():
        f_tree, inverse = parse_formula(row[F_FORMULA_COLUMN])
        f_vars = formula_variables(f_tree)
        if inverse and not has_variables(scenario_data, f_vars):
            matching.loc[i, [F_FORMULA_COLUMN, X_FORMULA_COLUMN]] = cropland[[F_FORMULA_COLUMN, X_FORMULA_COLUMN]].values
            print(f"[info] {scenario_name}: {', '.join(f_vars)} missing, "
                  f"'{row[STRESSOR_COLUMN]}' takes the '{YIELD_FALLBACK_STRESSOR}' row.")
    return matching


def check_variables(matching, scenario_data, nutrients_data, scenario_name):
    """Report the variables of the Matching sheet not found in the data."""
    for _, row in matching.iterrows():
        f_tree, _ = parse_formula(row[F_FORMULA_COLUMN])
        x_tree, _ = parse_formula(row[X_FORMULA_COLUMN])
        for tree, sources in [(f_tree, f_sources(row, scenario_data, nutrients_data)), (x_tree, [scenario_data])]:
            for v in formula_variables(tree):
                if not any(has_variables(source, [v]) for source in sources):
                    print(f"[info] {scenario_name}: variable '{v}' not found ({row[STRESSOR_COLUMN]}).")


def write_sheet(wb, sheet_name, matching, results, region_order):
    """(Re)create the sheet: 2 header rows (region code / F, x, S), then one row per stressor."""
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


def shift_columns(ws, col, delta):
    """Insert (delta = 1) or delete (delta = -1) column col, also shifting the
    column widths (not handled by openpyxl)."""
    widths = {column_index_from_string(letter): dim.width for letter, dim in ws.column_dimensions.items()}
    ws.insert_cols(col) if delta > 0 else ws.delete_cols(col)
    for index in sorted(widths, reverse=delta > 0):
        if index > col or (delta > 0 and index == col):
            ws.column_dimensions[get_column_letter(index + delta)].width = widths[index]


def add_world_columns(wb, excel_rows, world_s):
    """Write into the Matching sheet one "S 2050/2020 (World <scenario>)" column
    per scenario, values rounded to 2 decimals. The column of the reference
    scenario is overwritten in place (formulas included); the others are deleted
    then reinserted, in order, right after it.

    excel_rows: Excel row of each stressor; world_s: {scenario: [World S per stressor]}.
    """
    ws = wb[MATCHING_SHEET]
    is_world_s = lambda h: str(h).startswith(WORLD_S_HEADER)
    header_of = lambda name: f"{WORLD_S_HEADER} ({WORLD_LABEL} {name})"
    # Formatting taken from the first existing World S column
    template = next((cell for cell in ws[1] if is_world_s(cell.value)), None)
    template_format = None if template is None else (
        copy(template.font), copy(template.fill), copy(template.border), copy(template.alignment),
        ws.column_dimensions[template.column_letter].width)

    for name in world_s:
        headers = [cell.value for cell in ws[1]]
        if name != BASELINE_SCENARIO and header_of(name) in headers:
            shift_columns(ws, headers.index(header_of(name)) + 1, -1)

    for name, values in world_s.items():
        headers = [cell.value for cell in ws[1]]
        header = header_of(name)
        if header in headers:
            col, action = headers.index(header) + 1, "regenerated"
        else:
            col = max((i for i, h in enumerate(headers, start=1) if is_world_s(h)), default=ws.max_column) + 1
            shift_columns(ws, col, 1)
            cell = ws.cell(row=1, column=col, value=header)
            if template_format is not None:
                cell.font, cell.fill, cell.border, cell.alignment, width = template_format
                ws.column_dimensions[cell.column_letter].width = width
            action = "added"
        for r, value in zip(excel_rows, values):
            ws.cell(row=r, column=col, value=None if pd.isna(value) else round(float(value), 2))
        print(f"Column '{header}' {action} in sheet '{MATCHING_SHEET}'.")


def write_world_baseline_columns(wb, excel_rows, world_results):
    """Write the World F and x of the reference scenario into the existing
    columns of the Matching sheet, values rounded to 2 decimals.

    world_results: [(F, x, S) World per stressor] of the reference scenario.
    """
    ws = wb[MATCHING_SHEET]
    headers = [cell.value for cell in ws[1]]
    for header, k in WORLD_BASELINE_COLUMNS.items():
        if header not in headers:
            print(f"[info] Column '{header}' missing from sheet '{MATCHING_SHEET}', not written.")
            continue
        col = headers.index(header) + 1
        for r, values in zip(excel_rows, world_results):
            ws.cell(row=r, column=col, value=None if pd.isna(values[k]) else round(float(values[k]), 2))
        print(f"Column '{header}' regenerated in sheet '{MATCHING_SHEET}'.")


def main():
    matching = load_matching().dropna(subset=[STRESSOR_COLUMN])
    excel_rows = list(matching.index + 2)  # header on row 1
    matching = matching.reset_index(drop=True)
    image_map, gnm_map, region_order = load_region_maps()
    wb = openpyxl.load_workbook(MATCHING_FILE)

    baseline_data = load_scenario(SCENARIOS_DIR / f"{BASELINE_SCENARIO}.csv", image_map)
    baseline_nutrients = load_nutrients(BASELINE_SCENARIO, gnm_map)

    world_s = {}
    for csv_path in sorted(SCENARIOS_DIR.glob("*.csv")):
        scenario_name = csv_path.stem
        scenario_data = with_common_baseline(load_scenario(csv_path, image_map), baseline_data)
        nutrients_data = with_common_baseline(load_nutrients(scenario_name, gnm_map), baseline_nutrients)
        scenario_matching = apply_yield_fallback(matching, scenario_data, scenario_name)
        check_variables(scenario_matching, scenario_data, nutrients_data, scenario_name)
        results = {
            (i, region): compute_row(row, scenario_data, nutrients_data, region)
            for i, row in scenario_matching.iterrows()
            for region in region_order
        }
        neglected = [(excel_rows[i], region) for (i, region), values in results.items() if values[3]]
        if neglected:
            print(f"[info] {scenario_name}: S forced to 1 for {len(neglected)} cell(s) (2020 intensity "
                  f"< {MIN_RELATIVE_INTENSITY:g} x World): "
                  + ", ".join(f"row {r} {region}" for r, region in neglected))
        results = {key: values[:3] for key, values in results.items()}
        write_sheet(wb, scenario_name[:31], matching, results, region_order)
        print(f"Sheet '{scenario_name}' written.")
        world_s[scenario_name] = [results[(i, WORLD_REGION)][2] for i in range(len(matching))]
        if scenario_name == BASELINE_SCENARIO:
            write_world_baseline_columns(wb, excel_rows, [results[(i, WORLD_REGION)] for i in range(len(matching))])

    add_world_columns(wb, excel_rows, world_s)

    try:
        wb.save(MATCHING_FILE)
    except PermissionError:
        sys.exit(f"Cannot write {MATCHING_FILE}: close the file in Excel then run again.")
    print(f"Workbook written: {MATCHING_FILE}")


if __name__ == "__main__":
    main()
