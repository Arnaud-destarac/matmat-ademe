"""
Builds the scenario groups displayed by the figures (e.g. SSP_all, S1+,
Base_year) from the engine outputs, as declared in
Module_PlaneFR/data/scenario_groups.json.

Each group is a sub-folder of Module_PlaneFR/data/<version>/; each entry of the
file maps the displayed folder name to its source, a scenario folder written
by the pipeline (relative to data/<version>/, e.g. "no_SSP/S1_2050",
"SSP2_19_Sus_2050/S1_2050", "2019_FR"). For each entry, the target folder is
deleted then recreated as a copy of its source. Folders of a group that are not
declared in the file are left untouched and reported.

Run at the end of the pipeline, after compute_ds_x_dom.py: the copies then carry
the final F_Y_tot values (base year + manual shocks). The metadata.json of each
copy still records the accounts and shock it was computed with.

Safeguards:
    - a group must not be the parent folder of one of the sources (the engine
      output groups, such as no_SSP or SSP2_2050, are never overwritten);
    - every source must exist and be a scenario folder (with extensions/);
      otherwise nothing is copied and the script ends with exit code 1.

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
from planefr_paths import DATA_VERSION_DIR, MODULE_PLANEFR_DIR  # noqa: E402

GROUPS_FILE = MODULE_PLANEFR_DIR / "data" / "scenario_groups.json"


def load_groups():
    return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))["groups"]


def check_groups(groups):
    """List of error messages (empty if the groups can be built)."""
    errors = []
    source_parents = {source.split("/")[0] for entries in groups.values() for source in entries.values()}
    for group, entries in groups.items():
        if group in source_parents:
            errors.append(f"group '{group}' is also the parent folder of a source: it would overwrite engine outputs")
        for name, source in entries.items():
            if not (DATA_VERSION_DIR / source / "extensions").is_dir():
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

    groups = load_groups()
    if args.groups:
        unknown = sorted(set(args.groups) - set(groups))
        if unknown:
            sys.exit(f"Unknown groups: {unknown} (defined: {sorted(groups)})")
        groups = {g: groups[g] for g in args.groups}

    errors = check_groups(groups)
    if errors:
        print("Scenario groups not built:", *errors, sep="\n  ")
        sys.exit(1)

    for group, entries in groups.items():
        build_group(group, entries)
    print(f"{len(groups)} group(s) built in {DATA_VERSION_DIR}")


if __name__ == "__main__":
    main()
