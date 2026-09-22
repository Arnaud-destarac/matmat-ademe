"""
Pour chaque extension dans data/Monde/base-year_2015 et base-year_2019/extensions :
- transforme d_cba.pkl / F_x_dom.pkl / F_Y_tot.pkl en versions Monde, Europe et une par région Exiobase
- Monde  : supprime les Y_category indésirables, somme tout -> (region="World", Y_category="all", sector="all")
- Europe : idem mais en ne gardant que les 27 premières régions -> (region="Europe", ...)
- Région (hors FR) : idem mais en ne gardant qu'une seule région Exiobase (ex. "DK"...)
  -> (region=<code>, ...) ; mêmes fichiers (d_cba/F_x_dom/F_Y_tot) et même arborescence
  que Monde/Europe (dossier <ext_name>, pas de préfixe dom_), exportée dans 2019_<code>
  (une par région listée dans detail_levels.xlsx, UE et hors UE)
- France (FR) : cas particulier conservé tel quel -- seul F_Y_tot.pkl est exporté,
  dans dom_{ext_name}, car d_cba/F_x_dom pour la France proviennent déjà d'un autre
  pipeline (scénarios France dom_/imp_ existants dans data/3.10.2)

base-year_2015 (SRC_DIR[0]) ne produit qu'une version France, copiée dans tous
les autres dossiers de scénarios déjà présents dans data/3.10.2 (dom_{ext}) ;
base-year_2019 (SRC_DIR[1]) produit la version Monde, Europe, et une version par
région Exiobase, chacune dans son dossier dédié (2019_W, 2019_EU27, 2019_<code>).
"""

import os
import pickle
import shutil
import pandas as pd

# Chemins (relatifs à ce script, pas au répertoire de travail courant)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLANEFR_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "4-PlaneFR")

SRC_DIR = [
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "base-year_2015", "extensions"),
    os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "base-year_2019", "extensions"),
]

DATA_DIR = "C:\\Users\\Arnaud\\Documents\\CIRED\\PlaneFR\\Code\\Module_PlaneFR\\data\\3.10.2"
DST_MONDE = os.path.join(DATA_DIR, "2019_W", "extensions")
DST_EUROPE = os.path.join(DATA_DIR, "2019_EU27", "extensions")

# Y_categories à exclure. Ce label ("Exports: Total (fob)") est celui des données
# BRUTES en amont (SRC_DIR) ; il ne faut pas le confondre avec le label "Exports"
# utilisé par les notebooks d'analyse (planefr_lib.io.exclude_y_category), qui
# lisent eux les données déjà reformatées dans data/3.10.2 — deux étages du
# pipeline, deux libellés différents pour le même concept, pas une incohérence.
YCATS_EXCLUDED = {"Exports: Total (fob)"}

# Liste de toutes les régions Exiobase (UE puis hors UE / agrégats "Rest of World")
# issue du fichier de référence ; les 27 premières sont les régions européennes (UE).
DETAIL_LEVELS_PATH = os.path.join(PLANEFR_DATA_DIR, "Outputs", "World", "base-year_2019", "system", "detail_levels.xlsx")
with open(DETAIL_LEVELS_PATH, "rb") as f:
    _regions_df = pd.read_excel(f, sheet_name="regions")
ALL_REGIONS = _regions_df["region"].astype(str).to_list()
EU_REGIONS = ALL_REGIONS[:27]

# Une destination 2019_<code>/extensions par région Exiobase (ex. 2019_FR, 2019_DK...)
REGION_TARGETS = [(code, os.path.join(DATA_DIR, f"2019_{code}", "extensions")) for code in ALL_REGIONS]

# Découvrir dynamiquement les autres dossiers de scénarios déjà présents dans 3.10.2
# (scénarios France 2015, ex. Tech_NZE...) en excluant nos propres dossiers de sortie.
EXCLUDED_DIRS = {"2019_W", "2019_EU27"} | {f"2019_{code}" for code in ALL_REGIONS}
OTHER_DIRS = [
    os.path.join(DATA_DIR, d, "extensions")
    for d in os.listdir(DATA_DIR)
    if os.path.isdir(os.path.join(DATA_DIR, d, "extensions")) and d not in EXCLUDED_DIRS
]


def transform(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """
    mode='monde'  -> toutes les régions sauf Y_cats exclus, somme -> World/all/all
    mode='europe' -> 27 premières régions sauf Y_cats exclus, somme -> Europe/all/all
    mode=<code>   -> une seule région Exiobase (ex. 'FR', 'DK'...), somme -> <code>/all/all
    """
    if "Y_category" in df.columns.names:
        mask_ycat = ~df.columns.get_level_values("Y_category").isin(YCATS_EXCLUDED)
        df = df.loc[:, mask_ycat]

    if mode == "europe":
        df = df.loc[:, df.columns.get_level_values("region").isin(EU_REGIONS)]
    elif mode != "monde":
        df = df.loc[:, df.columns.get_level_values("region") == mode]

    totals = df.sum(axis=1)

    region_label = {"monde": "World", "europe": "Europe"}.get(mode, mode)
    if "Y_category" in df.columns.names:
        col_index = pd.MultiIndex.from_tuples([(region_label, "all", "all")], names=["region", "Y_category", "sector"])
    else:
        col_index = pd.MultiIndex.from_tuples([(region_label, "all")], names=["region", "sector"])

    return pd.DataFrame(totals.values, index=df.index, columns=col_index)


def _save_result(out_dir, filename, result, label):
    """Écrit `result` en pickle sous out_dir/filename (en créant les dossiers manquants), avec un log."""
    os.makedirs(out_dir, exist_ok=True)
    out_pkl = os.path.join(out_dir, filename)
    with open(out_pkl, "wb") as f:
        pickle.dump(result, f)
    print(f"  [{label.upper()}] {out_pkl}  shape={result.shape}")


def process_extension(ext_name: str, src_dir: str):
    srcs_pkl = [
        os.path.join(src_dir, ext_name, "d_cba.pkl"),
        os.path.join(src_dir, ext_name, "F_x_dom.pkl"),
        os.path.join(src_dir, ext_name, "F_Y_tot.pkl"),
    ]

    for src_pkl in srcs_pkl:
        if not os.path.exists(src_pkl):
            print(f"  [SKIP] {os.path.basename(src_pkl)} introuvable dans {ext_name}")
            continue

        with open(src_pkl, "rb") as f:
            df = pickle.load(f)

        # Certaines extensions (ex. raw_materials) arrivent avec un index MultiIndex
        # à un seul niveau (chaque clé est un tuple ('Primary Crops - Rice',)) au lieu
        # d'un Index plat de chaînes ('Primary Crops - Rice'). C'est un artefact de
        # cast_index_to_multiindex() côté pipeline d'extraction (sa contrepartie
        # convert_single_level_multi_index_to_regular_index() n'est jamais appelée) ;
        # on l'annule ici pour que l'index exporté soit plat.
        if isinstance(df.index, pd.MultiIndex) and df.index.nlevels == 1:
            df.index = df.index.get_level_values(0)

        if "source" in df.index.names:
            df = df.groupby(level="gas").sum()
            df.index.name = "indicator"

        if "Primary Crops - Rice" in df.index and "RMC" not in df.index:
            total = df.sum().rename("RMC").to_frame().T
            total.index.name = "indicator"
            df = pd.concat([df, total])

        filename = os.path.basename(src_pkl)

        if src_dir == SRC_DIR[0]:
            # base-year_2015 : une seule version France, dupliquée dans chaque
            # dossier de scénario déjà présent (ils partagent tous le même base year).
            # Ne s'applique que pour F_Y_tot.pkl (srcs_pkl[2]).
            if filename != "F_Y_tot.pkl" or (ext_name == "ghg_emissions" or ext_name == "raw_materials"):
                continue
            result = transform(df, "FR")
            for path in OTHER_DIRS:
                _save_result(os.path.join(path, f"dom_{ext_name}"), filename, result, "FR")
        else:
            targets = [("monde", DST_MONDE), ("europe", DST_EUROPE)] + REGION_TARGETS
            for mode, dst_base in targets:
                # Seule la France (FR) est traitée à part : les autres régions
                # suivent exactement le même traitement que Monde/Europe (les
                # 3 fichiers, dossier <ext_name> sans préfixe dom_).
                is_france = mode == "FR"
                if is_france and (filename != "F_Y_tot.pkl" or (ext_name == "ghg_emissions" or ext_name == "raw_materials")):
                    continue
                out_dir = os.path.join(dst_base, ext_name if not is_france else f"dom_{ext_name}")
                _save_result(out_dir, filename, transform(df, mode), mode)


def _clean_generated_outputs():
    """Supprime entièrement le dossier extensions/ de chaque sortie Monde/Europe/
    région (2019_W, 2019_EU27, 2019_<code>) avant de le régénérer -- SAUF 2019_FR.

    Monde/Europe/région (hors FR) sont entièrement produits par ce script : on
    peut donc les recréer de zéro sans perdre de données externes. 2019_FR, lui,
    n'est pas entièrement produit par ce script -- comme les scénarios France
    2015 dans OTHER_DIRS, il contient déjà des sous-dossiers dom_{ext}/imp_{ext}
    (d_cba.pkl, F_x_dom.pkl...) provenant d'un autre pipeline, dans lesquels ce
    script ne fait qu'ajouter dom_{ext}/F_Y_tot.pkl. Le supprimer effacerait ces
    données externes (vécu : un run précédent a écrasé 2019_FR de cette façon).
    """
    for mode, dst_base in [("monde", DST_MONDE), ("europe", DST_EUROPE)] + REGION_TARGETS:
        if mode == "FR":
            continue
        if os.path.isdir(dst_base):
            shutil.rmtree(dst_base)


def main():
    _clean_generated_outputs()

    for src_dir in SRC_DIR:
        extensions = [
            d for d in os.listdir(src_dir)
        ]
        print(f"{len(extensions)} extension(s) trouvée(s) : {extensions}\n")

        for ext in extensions:
            print(f"--- {ext} ---")
            process_extension(ext, src_dir)
            print()

    print("Terminé.")


if __name__ == "__main__":
    main()
