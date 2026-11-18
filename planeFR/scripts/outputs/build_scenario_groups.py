"""
Builds the scenario groups displayed by the figures (e.g. SSP_all, S1+,
Base_year) from the engine outputs, as declared in
Module_PlaneFR/data/Outputs_MatMat/scenario_groups.json.

Each group is a sub-folder of Module_PlaneFR/data/Outputs_MatMat/<version>/; each entry of the
file maps the displayed folder name to its source, a scenario folder written
by the pipeline (relative to data/<version>/, e.g. "2050_raw/no_SSP/S1_2050",
"2050_raw/SSP2_19_Sus_2050/S1_2050", "2019_raw/2019_FR"). The groups are built
directly in data/<version>/ (never in 2019_raw/ or 2050_raw/). For each entry, the target folder is
deleted then recreated as a copy of its source. Folders of a group that are not
declared in the file are left untouched and reported.

Run at the end of the pipeline, after compute_ds_x_dom.py: the copies then carry
the final F_Y_tot values (base year + manual shocks). The metadata.json of each
copy still records the accounts and shock it was computed with.

Safeguards:
    - a group must not be the parent folder of one of the sources (the engine
      output groups, such as no_SSP or SSP2_2050, are never overwritten);
    - every source must exist and be a scenario folder (with extensions/);
      otherwise nothing is copied and the script ends with exit code 1. A
      group none of whose sources exist yet (e.g. REGIONS_agri before the
      first planefr.py --Agri run) is only skipped, with a warning.

Agri-food variants: each declared group <G> also gives a group <G>_agri with
the same displayed names and the agri-food sources (agri_source:
2019_raw/2019_X -> 2019_X_agri, 2050_raw/<g>/<s> -> <g>_agri/<s>_agri,
Base_year_2015 -> Base_year_agri). It is skipped, with a warning, as long as
one of its sources is missing; declaring <G>_agri explicitly overrides it.

Usage:
    python build_scenario_groups.py [--groups SSP_all S1+]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Shared modules of planeFR/scripts/_common
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_common"))
from planefr_paths import DATA_VERSION_DIR, MODULE_OUTPUTS_DIR, RAW_DIR_NAMES  # noqa: E402

GROUPS_FILE = MODULE_OUTPUTS_DIR / "scenario_groups.json"


def load_groups():
    return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))["groups"]


AGRI_SUFFIX = "_agri"
# Reference scenario of the _agri engine groups (generate_shock_agri.py)
AGRI_BASE_YEAR = "Base_year_agri"


def agri_source(source):
    """Agri-food counterpart of a source: 2019_raw/2019_X -> 2019_raw/2019_X_agri;
    2050_raw/<group>/<scenario> -> 2050_raw/<group>_agri/<scenario>_agri, the
    2015 base year becoming Base_year_agri."""
    parts = source.split("/")
    if parts[0] == "2019_raw" and len(parts) == 2:
        return f"{source}{AGRI_SUFFIX}"
    if parts[0] == "2050_raw" and len(parts) == 3:
        _, group, scenario = parts
        scenario = AGRI_BASE_YEAR if scenario.startswith("Base_year") else f"{scenario}{AGRI_SUFFIX}"
        return f"2050_raw/{group}{AGRI_SUFFIX}/{scenario}"
    return None


def add_agri_groups(groups):
    """Adds <group>_agri for each declared group (same displayed names,
    agri-food sources, see agri_source), unless declared explicitly. A derived
    group with a source missing (e.g. --Agri not run yet) is skipped with a
    warning instead of failing the pipeline."""
    result = dict(groups)
    for group, entries in groups.items():
        name = f"{group}{AGRI_SUFFIX}"
        if group.endswith(AGRI_SUFFIX) or name in groups:
            continue
        derived = {display: agri_source(source) for display, source in entries.items()}
        missing = sorted(s or f"<no agri counterpart of {entries[d]}>" for d, s in derived.items()
                         if s is None or not _source_exists(s))
        if missing:
            print(f"[warn] {name}: not built, agri sources missing: {missing}")
            continue
        result[name] = derived
    return result


def _source_exists(source):
    return (DATA_VERSION_DIR / source / "extensions").is_dir()


def skip_unbuilt_groups(groups):
    """Groups none of whose sources exist yet (e.g. REGIONS_agri before the
    first planefr.py --Agri run) are skipped with a warning rather than
    failing the whole pipeline. A group with only SOME sources missing is
    still an error (see check_groups)."""
    kept = {}
    for group, entries in groups.items():
        if entries and not any(_source_exists(source) for source in entries.values()):
            print(f"[warn] {group}: none of its sources exist yet in {DATA_VERSION_DIR}, group not built")
            continue
        kept[group] = entries
    return kept


def check_groups(groups):
    """List of error messages (empty if the groups can be built)."""
    errors = []
    source_parents = {source.split("/")[0] for entries in groups.values() for source in entries.values()}
    for group, entries in groups.items():
        if group in source_parents or group in RAW_DIR_NAMES:
            errors.append(f"group '{group}' is also the parent folder of a source: it would overwrite engine outputs")
        for name, source in entries.items():
            if not _source_exists(source):
                errors.append(f"{group}/{name}: source '{source}' not found (or not a scenario folder) in {DATA_VERSION_DIR}")
    return errors


def build_group(group, entries):
    group_dir = DATA_VERSION_DIR / group
    group_dir.mkdir(parents=True, exist_ok=True)
    for name, source in entries.items():
        target = group_dir / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(DATA_VERSION_DIR / source, target)
        print(f"[copy] {group}/{name} <- {source}")
    undeclared = sorted(d.name for d in group_dir.iterdir() if d.is_dir() and d.name not in entries)
    if undeclared:
        print(f"[warn] {group}: folders not declared in {GROUPS_FILE.name}, left untouched: {undeclared}")


def main():
    parser = argparse.ArgumentParser(description="Builds the scenario groups of scenario_groups.json.")
    parser.add_argument("--groups", nargs="+", help="groups to build (all by default)")
    args = parser.parse_args()

    groups = add_agri_groups(load_groups())
    if args.groups:
        unknown = sorted(set(args.groups) - set(groups))
        if unknown:
            sys.exit(f"Unknown groups: {unknown} (defined: {sorted(groups)})")
        groups = {g: groups[g] for g in args.groups}

    groups = skip_unbuilt_groups(groups)
    errors = check_groups(groups)
    if errors:
        print("Scenario groups not built:", *errors, sep="\n  ")
        sys.exit(1)

    for group, entries in groups.items():
        build_group(group, entries)
    print(f"{len(groups)} group(s) built in {DATA_VERSION_DIR}")


if __name__ == "__main__":
    main()
