"""
Génère dS, la variation relative de S (= F_x_dom / x) entre 2020 et 2050, pour
chaque scénario SSP et chaque extension renseignés dans
Module_PlaneFR/data/SSP/Matching_extensions_EXIOBASE_IMAGE.xlsx.

Une feuille par scénario (SSP1, SSP2, ...). Chaque ligne de la feuille donne :
    - 'Domaine'            : l'extension (Air_emissions -> air_emissions, ...)
    - 'Extension EXIOBASE' : la (ou les) ligne(s) de S_x_dom à choquer
    - 'Secteurs EXIOBASE'  : les secteurs concernés, séparés par ';'
                             (case vide = tous les secteurs)
    - puis, par région IMAGE agrégée, trois sous-colonnes dont 'S 2050/2020'.

    dS = S 2050/2020 - 1

dS a le même format que S_x_dom.pkl de Base_year_2019 (indicateurs en ligne,
(region, sector) en colonne) et est initialisé à 0 ; seules les cellules
couvertes par le fichier de matching sont renseignées. Les régions EXIOBASE
sont rattachées aux régions IMAGE via la feuille 'regions' de bridge_SSPs.xlsx.

Correspondance des lignes : si 'Extension EXIOBASE' est exactement un
indicateur de S_x_dom, seul celui-ci est choqué ; sinon le libellé est découpé
sur ' - ' et tous les indicateurs contenant chacun des segments (sans tenir
compte de la casse) sont choqués, ex. 'Cropland - Wheat' -> 'Cropland -
cropped area - Wheat' et 'Cropland - fallowed area - Wheat'. Quand plusieurs
lignes du fichier couvrent la même cellule, la plus spécifique (celle qui
couvre le moins d'indicateurs) l'emporte. Cas particulier : les lignes
'Cropland' (SECTOR_IN_ROW_NAME) ne s'appliquent qu'aux indicateurs contenant
'Cropland' ET l'un des secteurs de 'Secteurs EXIOBASE', ex. 'Cropland' +
'Cattle' -> 'Cropland - fallowed area-Cattle'.

Secteurs : le choc ne s'applique qu'aux secteurs ayant une valeur non nulle
(dans au moins une région) pour l'indicateur considéré dans le S_x_dom de
Base_year_2019, en plus du filtre éventuel de 'Secteurs EXIOBASE'.

Régions : chaque région EXIOBASE est rattachée à une seule région IMAGE
agrégée ; toutes les régions EXIOBASE d'une même région IMAGE reçoivent le
même dS (ex. FR, DE, GB, CH, NO -> WEU).

dS_x_dom (.pkl et .xlsx) est écrit dans
MatMat/matmat-ademe/data/4-PlaneFR/2-shocks/3-SSPs_2050/<feuille>_2050/extensions/<ext>/
(dossiers créés s'ils n'existent pas), avec une copie du detail_levels.xlsx de
l'extension dans Base_year_2019. Le dossier <feuille>_2050/system/ reçoit de
même une copie du detail_levels.xlsx de Base_year_2019/system.

Chocs sur A : une ligne dont la colonne 'Domaine' contient une flèche
(A_SHOCK_MARKER, ex. 'Cultures → élevage') est un choc sur les coefficients
techniques A, et non sur S. 'Extension EXIOBASE' donne alors les secteurs EXIOBASE
en ligne de A (séparés par ';', toutes régions d'origine confondues) et
'Secteurs EXIOBASE' les secteurs en colonne. Pour chaque colonne (region,
sector), dA = S 2050/2020 - 1 de la région IMAGE de rattachement de la région
de la colonne (région qui consomme l'intrant). dA a le même format que le A.pkl
de Base_year_2019 (initialisé à 0) et est écrit en dA.pkl dans
<feuille>_2050/system/ (pas de .xlsx : 9800 x 9800 cellules).
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from compute_ds_x_dom import MATMAT_DIR, MODULE_PLANEFR_DIR, make_pickle_portable

MATCHING_FILE = MODULE_PLANEFR_DIR / "data" / "SSP" / "Matching_extensions_EXIOBASE_IMAGE.xlsx"
BRIDGE_FILE = MATMAT_DIR / "data" / "4-PlaneFR" / "Settings" / "4-engine" / "bridge_SSPs.xlsx"
BASE_YEAR_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "Outputs" / "World" / "Base_year_2019"
BASE_EXTENSIONS_DIR = BASE_YEAR_DIR / "extensions"
BASE_SYSTEM_DIR = BASE_YEAR_DIR / "system"
SHOCKS_OUTPUT_DIR = MATMAT_DIR / "data" / "4-PlaneFR" / "2-shocks" / "3-SSPs_2050"

NON_SCENARIO_SHEETS = {"Matching", "Régions", "Notes"}
S_RATIO_LABEL = "S 2050/2020"

# Marqueur, dans la colonne 'Domaine', d'un choc sur A (et non sur S)
A_SHOCK_MARKER = "→"

# Libellés du fichier de matching dont les segments ne se retrouvent pas tels
# quels dans les indicateurs EXIOBASE : segments à rechercher à la place.
ROW_ALIASES = {
    "Water Consumption Blue - Electricity - Electricity by hydro": [
        "Water Consumption Blue",
        "Electricity hydropower",
    ],
}

# Libellés dont les indicateurs choqués doivent en plus contenir l'un des
# secteurs de 'Secteurs EXIOBASE', ex. 'Cropland' + 'Cattle' ->
# 'Cropland - fallowed area-Cattle'.
SECTOR_IN_ROW_NAME = {"Cropland"}


def get_scenario_sheets():
    return [name for name in pd.ExcelFile(MATCHING_FILE).sheet_names if name not in NON_SCENARIO_SHEETS]


def load_region_bridge():
    """Région EXIOBASE -> région IMAGE agrégée (feuille 'regions' de bridge_SSPs.xlsx)."""
    bridge = pd.read_excel(BRIDGE_FILE, sheet_name="regions", header=[0, 1], index_col=[0, 1])
    bridge = bridge.droplevel(0, axis=0).droplevel(0, axis=1)
    return {exio: bridge.columns[bridge.loc[exio] == 1][0] for exio in bridge.index}


def load_scenario_shocks(sheet_name):
    """Reconstruit un tableau propre : la ligne 1 porte les noms de champ et les
    régions IMAGE (une région toutes les 3 colonnes), la ligne 2 les
    sous-colonnes (F, x, S 2050/2020) ; les données commencent ligne 3.
    Renvoie un DataFrame avec les colonnes domain, row_label, sectors puis une
    colonne par région IMAGE contenant S 2050/2020."""
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
    """Indicateurs de S_x_dom correspondant à un libellé 'Extension EXIOBASE'."""
    names = [ind[-1] if isinstance(ind, tuple) else ind for ind in indicators]
    if row_label in names:
        return [indicators[names.index(row_label)]]
    parts = ROW_ALIASES.get(row_label, [p.strip() for p in row_label.split(" - ")])
    parts = [p.lower() for p in parts]
    return [ind for ind, name in zip(indicators, names) if all(p in name.lower() for p in parts)]


def compute_ds(shocks, s_base, region_bridge):
    ds = pd.DataFrame(0.0, index=s_base.index, columns=s_base.columns)
    exio_regions = ds.columns.get_level_values("region")
    exio_sectors = ds.columns.get_level_values("sector")
    image_regions = exio_regions.map(region_bridge)

    rules = []
    for _, row in shocks.iterrows():
        label = row["row_label"]
        sectors = [] if pd.isna(row["sectors"]) else [s.strip() for s in str(row["sectors"]).split(";") if s.strip()]

        matched = match_indicators(label, list(ds.index))
        if label in SECTOR_IN_ROW_NAME and sectors:
            matched = [ind for ind in matched if any(s.lower() in ind[-1].lower() for s in sectors)]
        if not matched:
            print(f"[skip] '{label}' ({row['sectors']}) : aucun indicateur correspondant dans S_x_dom, ignoré.")
            continue

        if not sectors:
            sector_mask = pd.Series(True, index=ds.columns)
        else:
            unknown = sorted(set(sectors) - set(exio_sectors))
            if unknown:
                print(f"[warn] '{label}' : secteurs inconnus ignorés : {unknown}")
            sector_mask = pd.Series(exio_sectors.isin(sectors), index=ds.columns)

        # dS par colonne (region, sector), à partir de la région IMAGE de rattachement
        ds_cols = pd.Series(image_regions.map(lambda r: row.get(r)), index=ds.columns).astype(float) - 1
        ds_cols = ds_cols[sector_mask.values & ds_cols.notna().values]
        rules.append((len(matched), label, matched, ds_cols))

    # Les règles les plus génériques d'abord : les plus spécifiques écrasent ensuite
    for _, label, matched, ds_cols in sorted(rules, key=lambda r: -r[0]):
        n_cells = 0
        for ind in matched:
            # Seulement les secteurs EXIOBASE non nuls (dans au moins une région)
            # pour cet indicateur dans Base_year_2019
            s_row = s_base.loc[ind]
            active_sectors = set(s_row[s_row != 0].index.get_level_values("sector"))
            cols = ds_cols[ds_cols.index.get_level_values("sector").isin(active_sectors)]
            ds.loc[ind, cols.index] = cols.values
            n_cells += len(cols)
        print(f"[shock] '{label}' -> {len(matched)} indicateur(s), {n_cells} cellule(s)")

    return ds


def split_sectors(value):
    """Liste de secteurs EXIOBASE séparés par ';' (liste vide si case vide)."""
    return [] if pd.isna(value) else [s.strip() for s in str(value).split(";") if s.strip()]


def compute_da(shocks, a_index, a_columns, region_bridge):
    """dA (même format que A) : pour chaque ligne de choc, cellules (secteurs de
    'Extension EXIOBASE' toutes régions, secteurs de 'Secteurs EXIOBASE') =
    S 2050/2020 - 1 de la région IMAGE de la région de la colonne."""
    da = np.zeros((len(a_index), len(a_columns)))
    row_sectors_all = a_index.get_level_values("sector")
    col_sectors_all = a_columns.get_level_values("sector")
    image_regions = a_columns.get_level_values("region").map(region_bridge)

    for _, row in shocks.iterrows():
        label = f"{row['domain']} : {row['row_label']} x {row['sectors']}"
        row_sectors = split_sectors(row["row_label"])
        col_sectors = split_sectors(row["sectors"])
        for kind, sectors, known in (("lignes", row_sectors, row_sectors_all), ("colonnes", col_sectors, col_sectors_all)):
            unknown = sorted(set(sectors) - set(known))
            if unknown:
                print(f"[warn] '{row['domain']}' : secteurs ({kind}) inconnus ignorés : {unknown}")
        if not row_sectors or not col_sectors:
            print(f"[skip] '{label}' : secteurs en ligne ou en colonne manquants, ignoré.")
            continue

        da_cols = np.asarray(image_regions.map(lambda r: row.get(r)), dtype=float) - 1
        rows = np.flatnonzero(row_sectors_all.isin(row_sectors))
        cols = np.flatnonzero(col_sectors_all.isin(col_sectors) & ~np.isnan(da_cols))
        da[np.ix_(rows, cols)] = da_cols[cols]
        print(f"[shock A] '{row['domain']}' -> {len(rows)} ligne(s) x {len(cols)} colonne(s)")

    return pd.DataFrame(da, index=a_index, columns=a_columns)


def write_da_outputs(sheet_name, da):
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_2050" / "system"
    out_dir.mkdir(parents=True, exist_ok=True)
    make_pickle_portable(da).to_pickle(out_dir / "dA.pkl")
    print(f"[write] {out_dir / 'dA.pkl'}")


def write_ds_outputs(sheet_name, ext_name, ds):
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_2050" / "extensions" / ext_name
    out_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(ds.index, pd.MultiIndex):
        ds.index = pd.MultiIndex.from_arrays([ds.index], names=ds.index.names)
    make_pickle_portable(ds).to_pickle(out_dir / "dS_x_dom.pkl")
    ds.to_excel(out_dir / "dS_x_dom.xlsx", sheet_name="dS_x_dom")

    # detail_levels identique à celui de l'extension dans Base_year_2019
    shutil.copy2(BASE_EXTENSIONS_DIR / ext_name / "detail_levels.xlsx", out_dir / "detail_levels.xlsx")

    info_path = out_dir / "info.json"
    if not info_path.exists():
        info = {
            "base_year": "2019",
            "proj_year": "2050",
            "scenario_name": sheet_name,
            "extension_name": ext_name,
        }
        info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"[write] {out_dir / 'dS_x_dom.xlsx'} (+ .pkl, detail_levels.xlsx)")


def write_system_outputs(sheet_name):
    """detail_levels.xlsx de system identique à celui de Base_year_2019."""
    out_dir = SHOCKS_OUTPUT_DIR / f"{sheet_name}_2050" / "system"
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE_SYSTEM_DIR / "detail_levels.xlsx", out_dir / "detail_levels.xlsx")

    info_path = out_dir / "info.json"
    if not info_path.exists():
        info = {"base_year": "2019", "proj_year": "2050", "scenario_name": sheet_name}
        info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"[write] {out_dir / 'detail_levels.xlsx'}")


def main():
    region_bridge = load_region_bridge()
    a_index = a_columns = None

    for sheet_name in get_scenario_sheets():
        write_system_outputs(sheet_name)
        shocks = load_scenario_shocks(sheet_name)

        is_a_shock = shocks["domain"].str.contains(A_SHOCK_MARKER, regex=False)
        a_shocks, shocks = shocks[is_a_shock], shocks[~is_a_shock]
        if not a_shocks.empty:
            print(f"=== {sheet_name} / A ===")
            if a_index is None:
                # Seuls l'index et les colonnes de A servent : chargé une fois
                a_base = pd.read_pickle(BASE_SYSTEM_DIR / "A.pkl")
                a_index, a_columns = a_base.index, a_base.columns
                del a_base
            write_da_outputs(sheet_name, compute_da(a_shocks, a_index, a_columns, region_bridge))

        for domain, domain_shocks in shocks.groupby("domain", sort=False):
            ext_name = str(domain).strip().lower()
            print(f"=== {sheet_name} / {ext_name} ===")
            s_base = pd.read_pickle(BASE_EXTENSIONS_DIR / ext_name / "S_x_dom.pkl")
            ds = compute_ds(domain_shocks, s_base, region_bridge)
            write_ds_outputs(sheet_name, ext_name, ds)


if __name__ == "__main__":
    main()
