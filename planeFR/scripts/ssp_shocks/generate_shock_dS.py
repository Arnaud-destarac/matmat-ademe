"""
Generates dS, the relative variation of S (= F_x_dom / x) between 2020 and 2050,
for each SSP scenario and each stressor filled in in
Module_PlaneFR/data/Input_Shocks_MatMat/Matching_EXIOBASE_IMAGE.xlsx.

One sheet per scenario (SSP1, SSP2, ...). Each row of the sheet gives:
    - 'EXIOBASE groups'    : the extension (Air_emissions -> air_emissions, ...)
    - 'EXIOBASE stressors' : the row(s) of S_x_dom to shock
    - 'EXIOBASE products'  : the sectors concerned, separated by ';'
                             (empty cell = all the sectors)
    - then, by aggregated IMAGE region, three sub-columns including 'S 2050/2020'.

    dS = S 2050/2020 - 1

Base accounts: all the structural elements of the shocks (S_x_dom, A,
detail_levels.xlsx, base_year of the info.json files) are read in the World
accounts to which the engine applies these shocks, i.e. path_in.accounts of
settings_engine_SSPs.json (BASE_ACCOUNTS_DIR, e.g. Outputs/World/Base_year_2015;
see planefr_paths.get_ssp_base_accounts_dir). Changing the base year is
therefore done in a single place, this settings file, then by running this
script again.

dS has the same format as the S_x_dom.pkl of the base accounts (indicators as
rows, (region, sector) as columns) and is initialized to 0; only the cells
covered by the matching file are filled in. The EXIOBASE regions are attached
to the IMAGE regions through the 'regions' sheet of bridge_SSPs.xlsx.

Row matching: if the 'EXIOBASE stressors' label is exactly an indicator of
S_x_dom, only that one is shocked; otherwise the label is split on ' - ' and
all the indicators containing each of the segments (case-insensitive) are
shocked, e.g. 'Cropland - Wheat' -> 'Cropland - cropped area - Wheat' and
'Cropland - fallowed area - Wheat'. When several rows of the file cover the
same cell, the most specific one (the one covering the fewest indicators)
wins. Special case: the 'Cropland' rows (SECTOR_IN_ROW_NAME) only apply to the
indicators containing 'Cropland' AND one of the sectors of 'EXIOBASE products',
e.g. 'Cropland' + 'Cattle' -> 'Cropland - fallowed area-Cattle'.

Sectors: the shock only applies to the sectors with a non-zero value (in at
least one region) for the indicator considered in the S_x_dom of the base
accounts, in addition to the possible filter of 'EXIOBASE products'.

Regions: each EXIOBASE region is attached to a single aggregated IMAGE region;
all the EXIOBASE regions of a same IMAGE region get the same dS (e.g. FR, DE,
GB, CH, NO -> WEU).

dS_x_dom (.pkl only) is written into
MatMat/matmat-ademe/data/4-PlaneFR/2-shocks/3-SSPs_2050/<sheet>_2050/extensions/<ext>/
(folders created if they do not exist), with a copy of the detail_levels.xlsx of
the extension in the base accounts. The <sheet>_2050/system/ folder likewise
gets a copy of the detail_levels.xlsx of the system of the base accounts. The
info.json files (system and extensions) carry the base_year of the base
accounts and are updated at each run.

Shocks on A: a row whose 'EXIOBASE groups' column contains an arrow
(A_SHOCK_MARKER, e.g. 'Energy → Steel') is a shock on the technical
coefficients A, not on S. 'EXIOBASE stressors' then gives the EXIOBASE products
as rows of A (separated by ';', all regions of origin together) and
'EXIOBASE products' the sectors as columns. Each (region, sector) column gets
the IMAGE values of the IMAGE region its region is attached to (region
consuming the input). The shock is computed on the A of the base accounts, in
euros, in this order:

1. Single-factor groups (all the "→" groups except the next two, e.g.
   'Energy → Agriculture', 'Cultures → élevage', 'Primary fossil → Electricity'):
   A' = A x S 2050/2020 of the sheet of the scenario.
2. User groups ('Energy → <group>' with several rows, one per energy carrier;
   FE = sum of the 'F (IMAGE)' variables of the carriers that have one,
   act = 'x (IMAGE)'):
   - intensity I = [FE/act 2050] / [FE/act 2020] (1 if it cannot be computed,
     or if the 2020 intensity of the region is lower than MIN_RELATIVE_INTENSITY
     times that of the World); total energy of the column E' = I x E, E = sum
     of the coefficients of the products of the carriers of the group;
   - shares: Δv = share of v in FE in 2050 - share in 2020 (0 for a carrier
     without IMAGE variable), s'v = max(0, sv + Δv) renormalized, sv = euro
     share of v in E; total of the carrier = E' x s'v. Not applied to the
     HEAVY_GROUPS (central case: each carrier is only multiplied by I).
3. Electricity mix (ELECTRICITY_MIX_GROUP, one row per technology): same share
   computation on the technologies, total electricity of the technologies of
   the column kept. The electricity products outside the technologies
   (Electricity nec, transmission/distribution...) are not changed by this step.

Within a carrier (or a technology), the coefficients are scaled
proportionally (weights of the products and of the regions of origin kept).

The engine applies dA relatively (A = A0 x (1 + dA)): a zero coefficient in
A0 stays zero. dA = A'/A - 1 where A > 0, 0 elsewhere. For A' to be exactly
reached, a carrier (or a technology) missing from a column cannot appear in
it: the shares s'v are renormalized over the carriers present in the column
only, i.e. with a share >= MIN_VECTOR_SHARE (the total E', or the total
electricity, is kept; a carrier with a residual share is set to 0).
dA is written into <sheet>_2050/system/dA.pkl (no .xlsx: 9800 x 9800 cells).

Safeguard: before writing dA, the spectral radius of A' is computed. The
Leontief inverse (I - A')^-1 is only finite and positive if this radius is
< 1; beyond MAX_SPECTRAL_RADIUS (huge footprints or of any sign), no shock on A
is written for this scenario. The columns whose sum exceeds 1 and increases
(negative value added) are only reported.

Sector names: the matching file separates the sectors with ';' and therefore
writes ',' instead of the ';' of the EXIOBASE names (e.g. 'Wearing apparel, furs
(18)' for 'Wearing apparel; furs (18)'); the names are compared after replacing
';' by ',' and collapsing multiple spaces (sector_key).
"""

import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import ArpackNoConvergence, eigs

import extract_S_SSPs as ssp  # same folder; also adds _common to sys.path
from planefr_paths import MATMAT_DIR, PARAMETERS_DIR, get_ssp_base_accounts_dir
from planefr_utils import make_pickle_portable

MATCHING_FILE = ssp.MATCHING_FILE
BRIDGE_FILE = PARAMETERS_DIR / "4-engine" / "bridge_SSPs.xlsx"
# World accounts shocked by the engine (path_in.accounts of settings_engine_SSPs.json):
# single source of the structure and of the base year of the shocks (see docstring)
BASE_ACCOUNTS_DIR = get_ssp_base_accounts_dir()
BASE_EXTENSIONS_DIR = BASE_ACCOUNTS_DIR / "extensions"
BASE_SYSTEM_DIR = BASE_ACCOUNTS_DIR / "system"
SHOCKS_OUTPUT_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "2-shocks" / "3-SSPs_2050"
PROJ_YEAR = "2050"

NON_SCENARIO_SHEETS = {ssp.MATCHING_SHEET, ssp.REGIONS_SHEET, "Notes"}
S_RATIO_LABEL = "S 2050/2020"

# Marker, in the 'EXIOBASE groups' column, of a shock on A (and not on S)
A_SHOCK_MARKER = "→"
# The group labels below are data values of the 'EXIOBASE groups' column of
# the Matching file (compared after stripping spaces): change them here if they
# are renamed in the file.
# User groups (steps 1 and 2): groups starting with this prefix and having
# several rows (one per energy carrier)
ENERGY_GROUP_PREFIX = "Energy → "
# Electricity mix (step 3): one row per technology
ELECTRICITY_MIX_GROUP = "Electricity → All"
# Groups whose intensity only is shocked (EXIOBASE shares of the carriers
# kept); empty it to also apply the IMAGE shares to them (sensitivity)
HEAVY_GROUPS = {"Energy → Steel", "Energy → Chemicals", "Energy → Non-Metallic Minerals"}
# Maximum spectral radius allowed for A' (see check_shocked_a; 0.72 for A 2015)
MAX_SPECTRAL_RADIUS = 0.95
# Share (in euros) below which a carrier is considered missing from the column
# (residual coefficients, often imported, which would otherwise receive a whole
# IMAGE share: e.g. US biomass in the CA columns, x50 on CH4 combustion)
MIN_VECTOR_SHARE = 1e-2
DA_FILE = "dA.pkl"

# Labels of the matching file whose segments are not found as such in the
# EXIOBASE indicators: segments to search for instead.
ROW_ALIASES = {
    "Water Consumption Blue - Electricity - Electricity by hydro": [
        "Water Consumption Blue",
        "Electricity hydropower",
    ],
}

# Labels whose shocked indicators must also contain one of the sectors of
# 'EXIOBASE products', e.g. 'Cropland' + 'Cattle' ->
# 'Cropland - fallowed area-Cattle'.
SECTOR_IN_ROW_NAME = {"Cropland"}


def get_scenario_sheets():
    return [name for name in pd.ExcelFile(MATCHING_FILE).sheet_names if name not in NON_SCENARIO_SHEETS]


def load_region_bridge():
    """EXIOBASE region -> aggregated IMAGE region ('regions' sheet of bridge_SSPs.xlsx)."""
    bridge = pd.read_excel(BRIDGE_FILE, sheet_name="regions", header=[0, 1], index_col=[0, 1])
    bridge = bridge.droplevel(0, axis=0).droplevel(0, axis=1)
    return {exio: bridge.columns[bridge.loc[exio] == 1][0] for exio in bridge.index}


def load_scenario_shocks(sheet_name):
    """Rebuild a clean table: row 1 holds the field names and the IMAGE regions
    (one region every 3 columns), row 2 the sub-columns (F, x, S 2050/2020); the
    data start on row 3.
    Returns a DataFrame with the columns domain, row_label, sectors then one
    column per IMAGE region containing S 2050/2020."""
    raw = pd.read_excel(MATCHING_FILE, sheet_name=sheet_name, header=None)
    regions = raw.iloc[0].ffill()
    sub_labels = raw.iloc[1]
    data = raw.iloc[2:].reset_index(drop=True)

    shocks = pd.DataFrame(
        {"domain": data[0].str.strip(), "row_label": data[1].str.strip(), "sectors": data[2]}
    )
    for col in raw.columns[3:]:
        if sub_labels[col] == S_RATIO_LABEL:
            shocks[regions[col]] = pd.to_numeric(data[col], errors="coerce")
    return shocks.dropna(subset=["domain", "row_label"])


def match_indicators(row_label, indicators):
    """Indicators of S_x_dom matching an 'EXIOBASE stressors' label."""
    names = [ind[-1] if isinstance(ind, tuple) else ind for ind in indicators]
    if row_label in names:
        return [indicators[names.index(row_label)]]
    # Multi-level index, e.g. ('ghg_combustion', 'CO2') <-> 'ghg_combustion - CO2'
    full_names = [" - ".join(map(str, ind)) if isinstance(ind, tuple) else ind for ind in indicators]
    if row_label in full_names:
        return [indicators[full_names.index(row_label)]]
    parts = ROW_ALIASES.get(row_label, [p.strip() for p in row_label.split(" - ")])
    parts = [p.lower() for p in parts]
    return [ind for ind, name in zip(indicators, names) if all(p in name.lower() for p in parts)]


def compute_ds(shocks, s_base, region_bridge):
    ds = pd.DataFrame(0.0, index=s_base.index, columns=s_base.columns)
    exio_regions = ds.columns.get_level_values("region")
    exio_sectors = sector_keys(ds.columns.get_level_values("sector"))
    image_regions = exio_regions.map(region_bridge)

    rules = []
    for _, row in shocks.iterrows():
        label = row["row_label"]
        sectors = [] if pd.isna(row["sectors"]) else [s.strip() for s in str(row["sectors"]).split(";") if s.strip()]

        matched = match_indicators(label, list(ds.index))
        if label in SECTOR_IN_ROW_NAME and sectors:
            matched = [ind for ind in matched if any(s.lower() in ind[-1].lower() for s in sectors)]
        if not matched:
            print(f"[skip] '{label}' ({row['sectors']}): no matching indicator in S_x_dom, ignored.")
            continue

        if not sectors:
            sector_mask = pd.Series(True, index=ds.columns)
        else:
            unknown = sorted(set(sector_keys(sectors)) - set(exio_sectors))
            if unknown:
                print(f"[warn] '{label}': unknown sectors ignored: {unknown}")
            sector_mask = pd.Series(exio_sectors.isin(sector_keys(sectors)), index=ds.columns)

        # dS by (region, sector) column, from the IMAGE region it is attached to
        ds_cols = pd.Series(image_regions.map(lambda r: row.get(r)), index=ds.columns).astype(float) - 1
        ds_cols = ds_cols[sector_mask.values & ds_cols.notna().values]
        rules.append((len(matched), label, matched, ds_cols))

    # The most generic rules first: the most specific ones then overwrite them
    for _, label, matched, ds_cols in sorted(rules, key=lambda r: -r[0]):
        n_cells = 0
        for ind in matched:
            # Only the non-zero EXIOBASE sectors (in at least one region) for
            # this indicator in the base accounts
            s_row = s_base.loc[ind]
            active_sectors = set(s_row[s_row != 0].index.get_level_values("sector"))
            cols = ds_cols[ds_cols.index.get_level_values("sector").isin(active_sectors)]
            ds.loc[ind, cols.index] = cols.values
            n_cells += len(cols)
        print(f"[shock] '{label}' -> {len(matched)} indicator(s), {n_cells} cell(s)")

    return ds


def split_sectors(value):
    """List of EXIOBASE sectors separated by ';' (empty list if empty cell)."""
    return [] if pd.isna(value) else [s.strip() for s in str(value).split(";") if s.strip()]


def sector_key(name):
    """Sector name comparable between EXIOBASE and the matching file (see docstring)."""
    return re.sub(r"\s+", " ", str(name).replace(";", ",")).strip()


def sector_keys(names):
    return pd.Index([sector_key(name) for name in names])


def load_base_year():
    """base_year of the base accounts (system/info.json), carried over to the
    info.json files of the shocks."""
    info = json.loads((BASE_SYSTEM_DIR / "info.json").read_text(encoding="utf-8-sig"))
    return str(info["base_year"])


def load_engine_a():
    """A of the base accounts to which the engine applies the shock (BASE_ACCOUNTS_DIR)."""
    path = BASE_SYSTEM_DIR / "A.pkl"
    print(f"[A] base A: {path.resolve()}")
    return pd.read_pickle(path)


def write_info(info_path, **fields):
    """Write (or update) a shock info.json: the given fields replace those of
    an existing file, whose other fields are kept. A base_year inherited from a
    run on other base accounts is thus corrected."""
    info = json.loads(info_path.read_text(encoding="utf-8-sig")) if info_path.exists() else {}
    info.update(fields)
    info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")


def make_a_context(a_base, region_bridge):
    """Row/column markers of A used by the steps of the shock on A."""
    col_regions = np.asarray(a_base.columns.get_level_values("region"))
    return SimpleNamespace(
        columns=a_base.columns,
        row_keys=sector_keys(a_base.index.get_level_values("sector")),
        col_keys=sector_keys(a_base.columns.get_level_values("sector")),
        col_regions=col_regions,
        col_image_regions=np.asarray([region_bridge.get(r) for r in col_regions]),
    )


def select_rows(ctx, products):
    return np.flatnonzero(ctx.row_keys.isin(sector_keys(products)))


def select_cols(ctx, sectors):
    return np.flatnonzero(ctx.col_keys.isin(sector_keys(sectors)))


def warn_unknown_sectors(domain, products, sectors, ctx):
    for kind, names, known in (("rows", products, ctx.row_keys), ("columns", sectors, ctx.col_keys)):
        unknown = sorted(set(sector_keys(names)) - set(known))
        if unknown:
            print(f"[warn] '{domain}': unknown sectors ({kind}) ignored: {unknown}")


def load_a_rules():
    """Rows of shocks on A of the Matching sheet, by group: products (rows of A),
    sectors (columns) and IMAGE F and x formulas."""
    matching = ssp.load_matching().dropna(subset=[ssp.STRESSOR_COLUMN])
    rules = {}
    for _, row in matching.iterrows():
        domain = str(row[ssp.GROUP_COLUMN]).strip()
        if A_SHOCK_MARKER in domain:
            rules.setdefault(domain, []).append({
                "products": split_sectors(row[ssp.STRESSOR_COLUMN]),
                "sectors": split_sectors(row[ssp.PRODUCTS_COLUMN]),
                "f": row[ssp.F_FORMULA_COLUMN],
                "x": row[ssp.X_FORMULA_COLUMN],
            })
    return rules


def a_rule_kind(domain, n_rows):
    """'mix' (step 3), 'group' (steps 1 and 2) or 'factor' (single factor)."""
    if domain == ELECTRICITY_MIX_GROUP:
        return "mix"
    if domain.startswith(ENERGY_GROUP_PREFIX) and n_rows > 1:
        return "group"
    return "factor"


def load_image_data(sheet_name, image_map, baseline):
    """IMAGE data of the scenario (csv), common 2020 values (reference scenario)."""
    csv_by_sheet = {path.stem[:31]: path for path in ssp.SCENARIOS_DIR.glob("*.csv")}
    return ssp.with_common_baseline(ssp.load_scenario(csv_by_sheet[sheet_name], image_map), baseline)


def image_values(cell, data, region):
    """IMAGE [2020, 2050] values of the formula of a Matching cell; None if the
    cell has no formula or if the value cannot be computed."""
    tree, _ = ssp.parse_formula(cell)
    if tree is None:
        return None
    values = ssp.evaluate(tree, [data], region)
    return values if np.isfinite(values).all() else None


def share_deltas(values):
    """Δ = 2050 share - 2020 share of each carrier in the sum of the carriers
    with an IMAGE value (Δ = 0 for the others, or if the sum is zero)."""
    total = sum((v for v in values if v is not None), np.zeros(2))
    if total.min() <= 0:
        return np.zeros(len(values))
    return np.array([0.0 if v is None else v[1] / total[1] - v[0] / total[0] for v in values])


def group_targets(rows, data, regions):
    """By IMAGE region: (I, Δ per carrier) of a user group (see docstring)."""
    def levels(region):
        f_values = [image_values(row["f"], data, region) for row in rows]
        fe = sum((v for v in f_values if v is not None), np.zeros(2))
        act = next((v for v in (image_values(row["x"], data, region) for row in rows) if v is not None), None)
        with np.errstate(divide="ignore", invalid="ignore"):
            intensity = fe / act if act is not None else np.full(2, np.nan)
        return f_values, intensity

    _, world_intensity = levels(ssp.WORLD_REGION)
    targets = {}
    for region in regions:
        f_values, intensity = levels(region)
        i = intensity[1] / intensity[0] if intensity[0] > 0 else np.nan
        if not np.isfinite(i) or i < 0 or intensity[0] < ssp.MIN_RELATIVE_INTENSITY * world_intensity[0]:
            i = 1.0
        targets[region] = (i, share_deltas(f_values))
    return targets


def reshape_vectors(a_new, ctx, vector_rows, cols_all, targets, apply_shares):
    """Steps 1-2 (group) or 3 (mix, I = 1) on the columns cols_all: total of the
    carriers multiplied by I, then euro shares shifted by Δ if apply_shares, on
    the carriers present in the column only (see docstring). Each carrier is
    scaled proportionally to its coefficients.
    Returns the number of (missing carrier, column) pairs whose Δ > 0 could not
    be applied for lack of a coefficient to shock."""
    n_absent = 0
    for region, (i, delta) in targets.items():
        cols = cols_all[ctx.col_image_regions[cols_all] == region]
        if not len(cols):
            continue
        totals = np.array([a_new[np.ix_(rows, cols)].sum(axis=0) for rows in vector_rows])
        if apply_shares:
            energy = totals.sum(axis=0)
            shares = np.divide(totals, energy, out=np.zeros_like(totals), where=energy > 0)
            present = shares >= MIN_VECTOR_SHARE
            n_absent += int((~present & (energy > 0) & (delta[:, None] > 0)).sum())
            new_shares = np.where(present, np.maximum(0.0, shares + delta[:, None]), 0.0)
            norm = new_shares.sum(axis=0)
            new_shares = np.where(norm > 0, new_shares / np.where(norm > 0, norm, 1.0), shares)
            new_totals = i * energy * new_shares
        else:
            new_totals = i * totals
        for rows, vector_new_totals, vector_totals in zip(vector_rows, new_totals, totals):
            scale = np.divide(vector_new_totals, vector_totals, out=np.ones_like(vector_totals), where=vector_totals > 0)
            a_new[np.ix_(rows, cols)] *= scale
    return n_absent


def apply_factor_rules(a_new, ctx, factor_shocks):
    """Step 1 of the docstring: A' = A x S 2050/2020 (sheet of the scenario)."""
    for _, row in factor_shocks.iterrows():
        products, sectors = split_sectors(row["row_label"]), split_sectors(row["sectors"])
        warn_unknown_sectors(row["domain"], products, sectors, ctx)
        rows, cols_all = select_rows(ctx, products), select_cols(ctx, sectors)
        factors = np.asarray([row.get(r, np.nan) for r in ctx.col_image_regions[cols_all]], dtype=float)
        shocked = np.isfinite(factors) & (factors != 1)
        cols, factors = cols_all[shocked], factors[shocked]
        if len(rows) and len(cols):
            a_new[np.ix_(rows, cols)] *= factors
        print(f"[shock A] '{row['domain']}' (factor) -> {len(rows)} row(s) x {len(cols)} column(s)")


def compute_shocked_a(a_base, ctx, a_shocks, rules, data):
    """A' = shocked A (steps 1 to 3 of the docstring), as a numpy array."""
    a_new = a_base.copy()
    regions = sorted(r for r in set(ctx.col_image_regions) if r is not None)
    kinds = {domain: a_rule_kind(domain, len(rows)) for domain, rows in rules.items()}

    apply_factor_rules(a_new, ctx, a_shocks[a_shocks["domain"].map(kinds) == "factor"])

    for domain, rows in rules.items():
        if kinds[domain] != "group":
            continue
        sectors = sorted({s for row in rows for s in row["sectors"]})
        warn_unknown_sectors(domain, [p for row in rows for p in row["products"]], sectors, ctx)
        targets = group_targets(rows, data, regions)
        n_absent = reshape_vectors(
            a_new, ctx,
            vector_rows=[select_rows(ctx, row["products"]) for row in rows],
            cols_all=select_cols(ctx, sectors),
            targets=targets,
            apply_shares=domain not in HEAVY_GROUPS,
        )
        print(f"[shock A] '{domain}' ({'intensity' if domain in HEAVY_GROUPS else 'intensity + shares'}"
              f", {n_absent} missing carrier(s) x column(s) not created): I = "
              + ", ".join(f"{r} {i:.2f}" for r, (i, _) in targets.items()))

    for domain, rows in rules.items():
        if kinds[domain] != "mix":
            continue
        sectors = sorted({s for row in rows for s in row["sectors"]})
        warn_unknown_sectors(domain, [p for row in rows for p in row["products"]], sectors, ctx)
        deltas = {r: share_deltas([image_values(row["f"], data, r) for row in rows]) for r in regions}
        n_absent = reshape_vectors(
            a_new, ctx,
            vector_rows=[select_rows(ctx, row["products"]) for row in rows],
            cols_all=select_cols(ctx, sectors),
            targets={r: (1.0, delta) for r, delta in deltas.items()},
            apply_shares=True,
        )
        print(f"[shock A] '{domain}': {n_absent} missing technology(ies) x column(s) not created")

    return a_new


def spectral_radius(a):
    """Spectral radius of A (largest eigenvalue in modulus), np.inf if not converged."""
    try:
        return float(abs(eigs(csr_matrix(a), k=1, which="LM", return_eigenvectors=False, maxiter=5000)[0]))
    except ArpackNoConvergence:
        return np.inf


def check_shocked_a(a_new, a_base, ctx, sheet_name):
    """Return True if the spectral radius of A' is < MAX_SPECTRAL_RADIUS (finite
    and positive Leontief inverse). Also reports the columns whose sum exceeds 1
    and increases (negative value added)."""
    col_sums, base_sums = a_new.sum(axis=0), a_base.sum(axis=0)
    above = np.flatnonzero((col_sums >= 1) & (col_sums > base_sums + 1e-9))
    if len(above):
        print(f"[warn A] {sheet_name}: {len(above)} column(s) of A' with an increasing sum >= 1 "
              f"(negative value added):")
        for j in above[np.argsort(-col_sums[above])][:15]:
            print(f"    {ctx.columns[j]}: {base_sums[j]:.3f} -> {col_sums[j]:.3f}")

    rho, rho_base = spectral_radius(a_new), spectral_radius(a_base)
    if rho < MAX_SPECTRAL_RADIUS:
        print(f"[check A] {sheet_name}: spectral radius of A' = {rho:.4f} (base A: {rho_base:.4f})")
        return True
    print(f"[ERROR A] {sheet_name}: spectral radius of A' = {rho:.4f} >= {MAX_SPECTRAL_RADIUS:g} "
          f"(base A: {rho_base:.4f}): unreliable Leontief inverse, shock on A not written.")
    return False


def relative_shock(a_new, a_base):
    """dA = A'/A - 1 where A > 0, 0 elsewhere (A' = A x (1 + dA) in the engine),
    in place in a_new to limit memory use."""
    np.divide(a_new, a_base, out=a_new, where=a_base > 0)
    a_new -= 1.0
    a_new[a_base <= 0] = 0.0
    return a_new


def remove_da_output(sheet_name):
    """Delete a dA.pkl from a previous run, so as not to reuse it by mistake."""
    path = SHOCKS_OUTPUT_DIR / f"{sheet_name}_{PROJ_YEAR}" / "system" / DA_FILE
    if path.exists():
        path.unlink()
        print(f"[remove] {path}")


def write_da_outputs(sheet_name, da):
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_{PROJ_YEAR}" / "system"
    out_dir.mkdir(parents=True, exist_ok=True)
    make_pickle_portable(da).to_pickle(out_dir / DA_FILE)
    print(f"[write] {out_dir / DA_FILE}")


def write_ds_outputs(sheet_name, ext_name, ds, base_year):
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_{PROJ_YEAR}" / "extensions" / ext_name
    out_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(ds.index, pd.MultiIndex):
        ds.index = pd.MultiIndex.from_arrays([ds.index], names=ds.index.names)
    make_pickle_portable(ds).to_pickle(out_dir / "dS_x_dom.pkl")

    # detail_levels identical to that of the extension in the base accounts
    shutil.copy2(BASE_EXTENSIONS_DIR / ext_name / "detail_levels.xlsx", out_dir / "detail_levels.xlsx")

    write_info(
        out_dir / "info.json",
        base_year=base_year,
        proj_year=PROJ_YEAR,
        scenario_name=sheet_name,
        extension_name=ext_name,
    )
    print(f"[write] {out_dir / 'dS_x_dom.pkl'} (+ detail_levels.xlsx, info.json)")


def write_system_outputs(sheet_name, base_year):
    """detail_levels.xlsx of the system identical to that of the base accounts."""
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_{PROJ_YEAR}" / "system"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_SYSTEM_DIR / "detail_levels.xlsx", out_dir / "detail_levels.xlsx")

    write_info(out_dir / "info.json", base_year=base_year, proj_year=PROJ_YEAR, scenario_name=sheet_name)
    print(f"[write] {out_dir / 'detail_levels.xlsx'} (+ info.json)")


def main():
    region_bridge = load_region_bridge()
    base_year = load_base_year()
    print(f"[base] base accounts: {BASE_ACCOUNTS_DIR.resolve()} (base_year {base_year})")
    a_base = None

    for sheet_name in get_scenario_sheets():
        write_system_outputs(sheet_name, base_year)
        shocks = load_scenario_shocks(sheet_name)

        is_a_shock = shocks["domain"].str.contains(A_SHOCK_MARKER, regex=False)
        a_shocks, shocks = shocks[is_a_shock], shocks[~is_a_shock]
        if not a_shocks.empty:
            print(f"=== {sheet_name} / A ===")
            if a_base is None:
                # Loaded once for all the scenarios
                a_base_df = load_engine_a()
                a_base, ctx = a_base_df.to_numpy(), make_a_context(a_base_df, region_bridge)
                rules = load_a_rules()
                image_map, _, _ = ssp.load_region_maps()
                baseline = ssp.load_scenario(ssp.SCENARIOS_DIR / f"{ssp.BASELINE_SCENARIO}.csv", image_map)
            # The scenario sheets are generated from the Matching sheet by
            # extract_S_SSPs.py: a group missing from the Matching sheet means
            # they are out of date (e.g. groups renamed since the last run).
            unknown = sorted(set(a_shocks["domain"]) - set(rules))
            if unknown:
                raise ValueError(
                    f"Sheet '{sheet_name}': groups {unknown} not found in sheet '{ssp.MATCHING_SHEET}'. "
                    f"Run extract_S_SSPs.py first to regenerate the scenario sheets."
                )
            data = load_image_data(sheet_name, image_map, baseline)
            a_new = compute_shocked_a(a_base, ctx, a_shocks, rules, data)
            if check_shocked_a(a_new, a_base, ctx, sheet_name):
                da = relative_shock(a_new, a_base)
                write_da_outputs(sheet_name, pd.DataFrame(da, index=a_base_df.index, columns=a_base_df.columns))
            else:
                remove_da_output(sheet_name)
            del a_new

        for domain, domain_shocks in shocks.groupby("domain", sort=False):
            ext_name = str(domain).strip().lower()
            print(f"=== {sheet_name} / {ext_name} ===")
            s_base = pd.read_pickle(BASE_EXTENSIONS_DIR / ext_name / "S_x_dom.pkl")
            ds = compute_ds(domain_shocks, s_base, region_bridge)
            write_ds_outputs(sheet_name, ext_name, ds, base_year)


if __name__ == "__main__":
    main()
