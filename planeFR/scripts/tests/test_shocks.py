"""
Tests of the shock computations of planeFR/scripts, on small synthetic tables:

- formula parser of ssp_shocks/extract_S_SSPs.py (operators and precedence,
  units in parentheses, OR, max/min, yields "1 / ...", decimal comma) and the
  evaluation of the F, x and S 2050/2020 ratios;
- compute_ds of france_shocks/compute_ds_x_dom.py (inputs read in Excel are
  replaced by tables built here);
- compute_ds of ssp_shocks/generate_shock_dS.py, with its indicator matching,
  and the helpers of the shocks on A.

No Excel file and no MatMat run. Run from the root of matmat-ademe:

    uv run pytest planeFR/scripts/tests
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for sub in ("_common", "ssp_shocks", "france_shocks"):
    sys.path.insert(0, str(SCRIPTS_DIR / sub))

import compute_ds_x_dom  # noqa: E402
import extract_S_SSPs as ssp  # noqa: E402
import generate_shock_dS  # noqa: E402

V2020, V2050 = ssp.YEAR_BASE, ssp.YEAR_TARGET


def image_data(values):
    """IMAGE table as built by extract_S_SSPs.aggregate: index (Variable,
    Region), columns 2020 / 2050. values: {(variable, region): (v2020, v2050)}."""
    index = pd.MultiIndex.from_tuples(list(values), names=["Variable", "Region"])
    return pd.DataFrame(list(values.values()), index=index, columns=[V2020, V2050], dtype=float)


# === extract_S_SSPs: parser ===

@pytest.mark.parametrize("text, expected", [
    ("A (kgN/an) x (1 − B)", "A x (1 − B)"),
    ("A (Mt MS/an) + B (Mt)", "A + B"),
    ("(A + B) (Mt)", "(A + B)"),
    ("max (A, 0)", "max (A, 0)"),
    ("1 / Yield|Cereal (t/ha)", "1 / Yield|Cereal"),
])
def test_strip_units(text, expected):
    assert ssp.strip_units(text) == expected


@pytest.mark.parametrize("cell, tree", [
    ("A", ("var", "A")),
    ("A + B (Mt MS/an)", ("+", ("var", "A"), ("var", "B"))),
    ("A − B", ("-", ("var", "A"), ("var", "B"))),
    ("A + B x C", ("+", ("var", "A"), ("*", ("var", "B"), ("var", "C")))),
    ("A × B / C", ("/", ("*", ("var", "A"), ("var", "B")), ("var", "C"))),
    ("(A + B) x C", ("*", ("+", ("var", "A"), ("var", "B")), ("var", "C"))),
    ("A - B - C", ("-", ("-", ("var", "A"), ("var", "B")), ("var", "C"))),
    ("A x 0,5", ("*", ("var", "A"), ("num", 0.5))),
    ("A + B OU C", ("OR", ("+", ("var", "A"), ("var", "B")), ("var", "C"))),
    ("A OR B", ("OR", ("var", "A"), ("var", "B"))),
    ("max (A - B, 0)", ("max", ("-", ("var", "A"), ("var", "B")), ("num", 0.0))),
    ("min(A,B)", ("min", ("var", "A"), ("var", "B"))),
    ("Land Cover|Cropland|Energy Crops / Land Cover|Cropland",
     ("/", ("var", "Land Cover|Cropland|Energy Crops"), ("var", "Land Cover|Cropland"))),
    ("iNH3_volatization_arable (kgN/an) x (1 − Land Cover|Cropland|Energy Crops / Land Cover|Cropland)",
     ("*", ("var", "iNH3_volatization_arable"),
      ("-", ("num", 1.0), ("/", ("var", "Land Cover|Cropland|Energy Crops"), ("var", "Land Cover|Cropland"))))),
])
def test_parse_formula(cell, tree):
    assert ssp.parse_formula(cell) == (tree, False)


def test_parse_formula_inverse_yield():
    assert ssp.parse_formula("1 / Yield|Cereal (t/ha)") == (("var", "Yield|Cereal"), True)
    tree, inverse = ssp.parse_formula("1 / (A + B)")
    assert inverse and tree == ("+", ("var", "A"), ("var", "B"))


@pytest.mark.parametrize("cell", [None, np.nan, "", "–", "-", "  "])
def test_parse_formula_empty_cells(cell):
    assert ssp.parse_formula(cell) == (None, False)


@pytest.mark.parametrize("cell", ["(A + B", "max (A)", "A B )", "A + )"])
def test_parse_formula_invalid(cell):
    with pytest.raises(ValueError, match="Invalid formula"):
        ssp.parse_formula(cell)


def test_formula_variables_unique_in_order():
    tree, _ = ssp.parse_formula("B x (A + B) / 2 OR C")
    assert ssp.formula_variables(tree) == ["B", "A", "C"]
    assert ssp.formula_variables(None) == []


# === extract_S_SSPs: evaluation ===

def test_evaluate_operators_and_functions():
    data = image_data({("A", "R"): (4, 8), ("B", "R"): (1, 2)})
    evaluate = lambda cell: ssp.evaluate(ssp.parse_formula(cell)[0], [data], "R").tolist()  # noqa: E731
    assert evaluate("A + B x 2") == [6, 12]
    assert evaluate("(A − B) / B") == [3, 3]
    assert evaluate("max (B - 1,5, 0)") == [0, 0.5]
    assert evaluate("min (A, 5)") == [4, 5]
    assert evaluate("A / 0") == pytest.approx([np.nan, np.nan], nan_ok=True)
    assert np.isnan(evaluate("Unknown + A")).all()


def test_evaluate_or_falls_back_when_negative():
    data = image_data({("A", "R"): (2, -1), ("B", "R"): (5, 6), ("A", "S"): (2, 3)})
    tree, _ = ssp.parse_formula("A OU B")
    assert ssp.evaluate(tree, [data], "R").tolist() == [5, 6]  # A < 0 in 2050
    assert ssp.evaluate(tree, [data], "S").tolist() == [2, 3]


def test_lookup_values_uses_first_source_containing_variable():
    first = image_data({("A", "R"): (1, 2)})
    second = image_data({("A", "R"): (10, 20), ("B", "R"): (3, 4)})
    assert ssp.lookup_values([first, second], "A", "R").tolist() == [1, 2]
    assert ssp.lookup_values([first, second], "B", "R").tolist() == [3, 4]
    assert np.isnan(ssp.lookup_values([first], "B", "R")).all()


def test_ratio():
    data = image_data({("A", "R"): (2, 3), ("Z", "R"): (0, 3)})
    assert ssp.ratio(ssp.parse_formula("A")[0], [data], "R") == 1.5
    assert np.isnan(ssp.ratio(ssp.parse_formula("Z")[0], [data], "R"))  # 2020 = 0
    assert np.isnan(ssp.ratio(None, [data], "R"))


def matching_row(f, x, group="Air_emissions"):
    return pd.Series({ssp.GROUP_COLUMN: group, ssp.F_FORMULA_COLUMN: f, ssp.X_FORMULA_COLUMN: x})


def test_compute_row_s_is_f_over_x():
    data = image_data({("F", "R"): (10, 30), ("X", "R"): (5, 10),
                       ("F", "World"): (100, 100), ("X", "World"): (50, 50)})
    f, x, s, negligible = ssp.compute_row(matching_row("F (Mt)", "X"), data, image_data({}), "R")
    assert (f, x, s, negligible) == (3.0, 2.0, 1.5, False)


def test_compute_row_negligible_intensity_forces_s_to_one():
    data = image_data({("F", "R"): (1e-6, 1), ("X", "R"): (1, 1),
                       ("F", "World"): (1, 1), ("X", "World"): (1, 1)})
    f, x, s, negligible = ssp.compute_row(matching_row("F", "X"), data, image_data({}), "R")
    assert (s, negligible) == (1.0, True)
    assert f == pytest.approx(1e6)


def test_compute_row_inverse_yield():
    data = image_data({("Yield|Cereal", "R"): (2, 4), ("X", "R"): (1, 3)})
    f, x, s, negligible = ssp.compute_row(matching_row("1 / Yield|Cereal (t/ha)", "X"), data,
                                          image_data({}), "R")
    # F = ratio of 1 / yield = S
    assert (f, s, x, negligible) == (0.5, 0.5, 3.0, False)


def test_compute_row_missing_data_gives_s_one():
    data = image_data({("X", "R"): (1, 2)})
    f, x, s, _ = ssp.compute_row(matching_row("F", "X"), data, image_data({}), "R")
    assert np.isnan(f) and x == 2.0 and s == 1.0


def test_compute_row_nutrients_group_reads_nutrients_first():
    scenario = image_data({("N", "R"): (1, 10), ("X", "R"): (1, 1)})
    nutrients = image_data({("N", "R"): (1, 2)})
    row = matching_row("N", "X", group=ssp.NUTRIENTS_GROUP)
    assert ssp.compute_row(row, scenario, nutrients, "R")[0] == 2.0
    assert ssp.compute_row(matching_row("N", "X"), scenario, nutrients, "R")[0] == 10.0


def test_with_world_fallback_replaces_missing_or_zero_world():
    data = image_data({("A", "R1"): (1, 2), ("A", "R2"): (3, 4), ("A", "World"): (0, 0),
                       ("B", "R1"): (1, 1), ("B", "World"): (9, 9)})
    out = ssp.with_world_fallback(data)
    assert out.loc[("A", "World")].tolist() == [4, 6]
    assert out.loc[("B", "World")].tolist() == [9, 9]


# === compute_ds_x_dom.compute_ds ===

def manual_shocks(rows):
    """Table of load_manual_shocks: variable, row_name, then one column per scenario."""
    columns = ["variable", "row_region", "row_name", "c3", "c4", "c5", "c6", *compute_ds_x_dom.SCENARIO_FOLDER_NAMES]
    return pd.DataFrame([[variable, None, name, None, None, None, None, *shocks]
                         for variable, name, shocks in rows], columns=columns)


def test_compute_ds_x_dom(monkeypatch):
    sectors = pd.MultiIndex.from_tuples([("FR", "s1"), ("FR", "s2"), ("FR", "s3")], names=["region", "sector"])
    f_base = pd.DataFrame([[10.0, 0.0, 4.0], [1.0, 1.0, 1.0]], index=["CO2", "CH4"], columns=sectors)
    x_dom = pd.DataFrame([[100.0, 50.0, 10.0], [200.0, 50.0, 0.0]],
                         index=[compute_ds_x_dom.BASE_YEAR_NAME, "S1_2050"], columns=sectors)
    for name in ("S2_2050", "S3_2050", "S4_2050", "TEND_2050"):
        x_dom.loc[name] = x_dom.loc[compute_ds_x_dom.BASE_YEAR_NAME]
    shocks = manual_shocks([
        ("F_x_dom", "CO2", [-0.5, 0.0, np.nan, 0.2, 0.0]),
        ("F_x_dom", "Unknown", [1.0, 1.0, 1.0, 1.0, 1.0]),
        ("F_Y_tot", "CH4", [1.0, 1.0, 1.0, 1.0, 1.0]),
    ])
    monkeypatch.setattr(compute_ds_x_dom, "load_f_x_dom_base", lambda lp: f_base)
    monkeypatch.setattr(compute_ds_x_dom, "load_manual_shocks", lambda lp: shocks)

    ds = compute_ds_x_dom.compute_ds("ghg", x_dom)

    assert set(ds) == set(compute_ds_x_dom.SCENARIO_FOLDER_NAMES)
    # S1: dS = (1 - 0.5) x x_base / x_2050 - 1; s2 (F = 0) -> NaN -> 0; s3 (x 2050 = 0) -> inf -> 0
    assert ds["S1"].loc["CO2"].tolist() == pytest.approx([0.5 * 100 / 200 - 1, 0.0, 0.0])
    assert (ds["S1"].loc["CH4"] == 0).all()  # F_Y_tot shock: not a dS
    # S4: same x as the base year -> dS = shock where F != 0
    assert ds["S4"].loc["CO2"].tolist() == pytest.approx([0.2, 0.0, 0.2])
    # Shock 0 or empty: not calibrated, dS stays 0
    for short in ("S2", "S3", "TEND"):
        assert (ds[short] == 0).all().all()
        assert ds[short].index.equals(f_base.index) and ds[short].columns.equals(sectors)


def manual_param_rows(scenarios=("S1", "S2", "S3", "S4", "TEND"), title_rows=0):
    """Layout of a dom_<lp> sheet of my_manual_param.xlsx: scenario names, year
    row, field row, then the shocks."""
    fields = ["variable", "row_region", "row_name", "row_level", "col_region", "col_name", "col_level"]
    blank = [None] * len(fields)
    return ([["Title"] + [None] * (len(fields) + len(scenarios) - 1)] * title_rows
            + [blank + list(scenarios), blank + [2050] * len(scenarios), fields + [None] * len(scenarios),
               ["F_x_dom", ":", "CO2", "indicator", ":", ":", "sector", *[0.1 * (i + 1) for i in range(len(scenarios))]],
               ["F_Y_tot", ":", "CH4", "indicator", ":", ":", ":", *[0.0] * len(scenarios)]])


def use_manual_param(monkeypatch, tmp_path, rows):
    path = tmp_path / "my_manual_param.xlsx"
    pd.DataFrame(rows).to_excel(path, sheet_name="dom_ghg", header=False, index=False)
    monkeypatch.setattr(compute_ds_x_dom, "MANUAL_PARAM_FILE", path)


@pytest.mark.parametrize("scenarios, title_rows", [
    (("S1", "S2", "S3", "S4", "TEND"), 0),
    (("TEND", "S4", "S3", "S2", "S1"), 0),  # columns reordered
    (("S1", "S2", "S3", "S4", "TEND"), 2),  # rows added above
])
def test_load_manual_shocks_by_content(monkeypatch, tmp_path, scenarios, title_rows):
    use_manual_param(monkeypatch, tmp_path, manual_param_rows(scenarios, title_rows))
    shocks = compute_ds_x_dom.load_manual_shocks("ghg")
    assert list(shocks.columns[:7]) == ["variable", "row_region", "row_name", "row_level",
                                        "col_region", "col_name", "col_level"]
    assert sorted(shocks.columns[7:]) == sorted(compute_ds_x_dom.SCENARIO_FOLDER_NAMES)
    co2 = shocks[shocks["row_name"] == "CO2"].iloc[0]
    assert {s: co2[s] for s in scenarios} == pytest.approx({s: 0.1 * (i + 1) for i, s in enumerate(scenarios)})


@pytest.mark.parametrize("scenarios, error", [
    (("S1", "S2", "S3", "S4"), "not found"),
    (("S1", "S2", "S3", "S4", "TEND", "S1"), "several columns"),
])
def test_load_manual_shocks_bad_scenarios_raise(monkeypatch, tmp_path, scenarios, error):
    use_manual_param(monkeypatch, tmp_path, manual_param_rows(scenarios))
    with pytest.raises(ValueError, match=error):
        compute_ds_x_dom.load_manual_shocks("ghg")


def test_load_manual_shocks_missing_fields_raise(monkeypatch, tmp_path):
    rows = manual_param_rows()
    rows[2][2] = "name"  # "row_name" renamed
    use_manual_param(monkeypatch, tmp_path, rows)
    with pytest.raises(ValueError, match="no row with the fields"):
        compute_ds_x_dom.load_manual_shocks("ghg")


# === generate_shock_dS ===

INDICATORS = ["Cropland - cropped area - Wheat", "Cropland - fallowed area - Wheat",
              "Cropland - fallowed area-Cattle", "CO2", "Water Consumption Blue - Electricity hydropower"]


def s_base_table():
    """S_x_dom of the base accounts: (indicator,) rows -- 1-level MultiIndex,
    as written by the engine -- and (region, sector) columns."""
    columns = pd.MultiIndex.from_product([["FR", "DE", "CN"], ["Wheat", "Cattle", "Wearing apparel; furs (18)"]],
                                         names=["region", "sector"])
    index = pd.MultiIndex.from_arrays([INDICATORS], names=["indicator"])
    values = np.ones((len(index), len(columns)))
    values[3, columns.get_loc(("FR", "Cattle"))] = 0.0
    values[3, columns.get_loc(("DE", "Cattle"))] = 0.0
    return pd.DataFrame(values, index=index, columns=columns)


def test_match_indicators():
    indicators = INDICATORS
    match = generate_shock_dS.match_indicators
    assert match("CO2", indicators) == ["CO2"]
    assert match("Cropland - Wheat", list(s_base_table().index)) == [(INDICATORS[0],), (INDICATORS[1],)]
    assert match("Cropland - Wheat", indicators) == indicators[:2]
    assert match("Water Consumption Blue - Electricity - Electricity by hydro", indicators) == [indicators[4]]
    assert match("Nothing", indicators) == []
    multi = [("ghg_combustion", "CO2"), ("ghg_combustion", "CH4")]
    assert match("ghg_combustion - CH4", multi) == [multi[1]]
    assert match("CO2", multi) == [multi[0]]


def test_sector_key():
    assert generate_shock_dS.sector_key("Wearing apparel;  furs (18)") == "Wearing apparel, furs (18)"
    assert generate_shock_dS.split_sectors(" Wheat ; Cattle;") == ["Wheat", "Cattle"]
    assert generate_shock_dS.split_sectors(np.nan) == []


def test_generate_compute_ds():
    s_base = s_base_table()
    bridge = {"FR": "WEU", "DE": "WEU", "CN": "CHN"}
    shocks = pd.DataFrame([
        # generic rule (2 indicators), then a more specific one on the same cells
        {"domain": "Land", "row_label": "Cropland - Wheat", "sectors": np.nan, "WEU": 2.0, "CHN": 0.5},
        {"domain": "Land", "row_label": "Cropland - fallowed area - Wheat", "sectors": "Wheat", "WEU": 3.0,
         "CHN": np.nan},
        # Cropland: only the indicators containing one of the sectors
        {"domain": "Land", "row_label": "Cropland", "sectors": "Cattle", "WEU": 1.5, "CHN": 1.5},
        # sector name written with ',' in the matching file
        {"domain": "Air", "row_label": "CO2", "sectors": "Wearing apparel, furs (18); Cattle", "WEU": 0.8,
         "CHN": 1.2},
        {"domain": "Air", "row_label": "Unknown", "sectors": np.nan, "WEU": 9.0, "CHN": 9.0},
    ])

    ds = generate_shock_dS.compute_ds(shocks, s_base, bridge)
    cropped, fallowed, cattle, co2 = (ds.loc[(i,)] for i in INDICATORS[:4])

    assert cropped[("FR", "Wheat")] == 1.0 and cropped[("CN", "Wheat")] == -0.5
    assert cropped[("FR", "Cattle")] == 1.0  # no sector filter
    assert fallowed[("FR", "Wheat")] == 2.0  # specific rule wins
    assert fallowed[("CN", "Wheat")] == -0.5  # specific rule has no CHN value: generic kept
    assert fallowed[("FR", "Cattle")] == 1.0  # outside the specific rule's sectors
    assert cattle[("FR", "Cattle")] == 0.5 and cattle[("FR", "Wheat")] == 0.0
    # S = 0 for (FR|DE, Cattle) only, but the sector is active in CN: shocked everywhere
    assert co2[("FR", "Cattle")] == pytest.approx(-0.2) and co2[("CN", "Cattle")] == pytest.approx(0.2)
    assert co2[("DE", "Wearing apparel; furs (18)")] == pytest.approx(-0.2)
    assert co2[("FR", "Wheat")] == 0.0
    assert (ds.loc[(INDICATORS[4],)] == 0).all()


def test_generate_compute_ds_skips_inactive_sectors():
    s_base = s_base_table()
    s_base.loc[("CO2",), (slice(None), "Cattle")] = 0.0  # Cattle never emits CO2
    shocks = pd.DataFrame([{"domain": "Air", "row_label": "CO2", "sectors": np.nan, "WEU": 2.0, "CHN": 2.0}])
    ds = generate_shock_dS.compute_ds(shocks, s_base, {"FR": "WEU", "DE": "WEU", "CN": "CHN"})
    co2 = ds.loc[("CO2",)]
    assert (co2[(slice(None), "Cattle")] == 0).all()
    assert (co2[(slice(None), "Wheat")] == 1.0).all()


def test_share_deltas():
    deltas = generate_shock_dS.share_deltas([np.array([1.0, 3.0]), None, np.array([1.0, 1.0])])
    assert deltas.tolist() == pytest.approx([0.75 - 0.5, 0.0, 0.25 - 0.5])
    assert generate_shock_dS.share_deltas([np.array([0.0, 1.0])]).tolist() == [0.0]


def test_relative_shock():
    a_base = np.array([[0.2, 0.0], [0.5, 0.1]])
    a_new = np.array([[0.3, 0.4], [0.5, 0.05]])
    da = generate_shock_dS.relative_shock(a_new, a_base)
    np.testing.assert_allclose(da, [[0.5, 0.0], [0.0, -0.5]])


def test_a_rule_kind():
    kind = generate_shock_dS.a_rule_kind
    assert kind(generate_shock_dS.ELECTRICITY_MIX_GROUP, 5) == "mix"
    assert kind("Energy → Steel", 3) == "group"
    assert kind("Energy → Agriculture", 1) == "factor"
    assert kind("Primary fossil → Electricity", 4) == "factor"
