"""
Single command of the PlaneFR pipeline: chains the MatMat runs and the Python
scripts of planeFR/scripts, on Windows and Linux alike.

Usage, from the root of matmat-ademe (any folder works, the paths are derived
from the location of this file). Simplest: say what has changed.

    uv run python planeFR/scripts/planefr.py --All [--version 3.11.2]
        -> base accounts (1-exiobase3_eeio, extract_f_y_tot, 2-gmrio_to_snac_s,
           3-update_calib_fr, which only depend on Exiobase and the France
           calibration), then france-shocks, ssp-shocks and outputs
    uv run python planeFR/scripts/planefr.py --RoW_shocks_change
        -> ssp-shocks, then outputs --ssps
    uv run python planeFR/scripts/planefr.py --France_shocks_change
        -> france-shocks, then outputs
    uv run python planeFR/scripts/planefr.py --France_shocks_dS_change
        -> france-shocks --manual-only, then outputs
    uv run python planeFR/scripts/planefr.py --Agri
        -> agri (_agri shocks from the current France and SSP shocks, then
           the outputs stages with the _agri suffix)

--Agri can be combined with the other four (e.g. --France_shocks_change
--Agri): only the _agri part affected by the change is recomputed (no _agri
projected world after a French change, SSP groups only after an SSP change),
and the post-processing runs once for both variants (Pipeline.chain_change).
To generate only some outputs, add --France and/or --RoW (names
without suffix, listed at the end of --help): the pairs generated are the
combinations of both lists, e.g. --France S1_2050 --RoW no_SSP
SSP2_2050 gives no_SSP/S1_2050 and SSP2_2050/S1_2050. It applies to the final
France engine of outputs, agri and the change options (the baselines
Base_year_2015 and 2019_FR are then not recomputed; the post-processing still
processes every folder).

The change options can also be combined with each other, e.g.
--France_shocks_change --RoW_shocks_change [--Agri]: both shock chains, then a
single France engine pass and post-processing (All without the base accounts).

Or run a chain directly:

    uv run python planeFR/scripts/planefr.py france-shocks [--manual-only] [--version 3.11.2]
    uv run python planeFR/scripts/planefr.py ssp-shocks [--version 3.11.2]
    uv run python planeFR/scripts/planefr.py outputs [--ssps] [--version 3.11.2]
    uv run python planeFR/scripts/planefr.py agri [--version 3.11.2]
    uv run python planeFR/scripts/planefr.py step <name> [--suffix _agri] [--reference <scenario>]

Chains (each stage is named after the folder of planeFR/scripts holding it).
france-shocks and ssp-shocks each regenerate one set of shocks; outputs then
computes all the output groups from the current shocks. After a change, run
the shock chain(s) concerned, then outputs:

    france-shocks  after a change to the French shocks (my_manual_param.xlsx,
                   system shocks of 1-transitions_2050): France engine on the
                   no_SSP group only, the reformat scripts, export_dS,
                   compute_ds_x_dom (which also writes the detail_levels.xlsx /
                   info.json of the shocked extensions). This engine run only provides the 2050
                   production x, which does not depend on the intensity shocks
                   dS_x_dom: a single pass gives exact dS_x_dom.
                   --manual-only: when only my_manual_param.xlsx has changed,
                   x and S_extraction.xlsx are still valid: only runs
                   compute_ds_x_dom.
    ssp-shocks     after a change to the SSP shocks (IMAGE scenarios, Matching
                   workbook, base year of the SSP shocks): ssp_shocks/
                   (extract_S_SSPs, generate_shock_dS), then the rest of the
                   world projected on each SSP (World engine, gmrio_to_snac_s,
                   update_calib_fr), which only depends on these shocks.
    outputs        all the output groups (no_SSP, SSP2_2050...) from the current
                   shocks: France engine on every accounts x French scenario
                   pair, the reformat scripts, compute_ds_x_dom --only-f-y-tot (reapplies
                   the F_Y_tot shocks), build_scenario_groups. --ssps: France
                   engine on the SSP groups only (all the accounts folders
                   except no_SSP, found automatically), since a change to the
                   SSP shocks does not change no_SSP.
    agri           "_agri" variant of outputs: generate_shock_agri (from the
                   current French and SSP shocks), the rest of the world
                   projected on the _agri SSP shocks, the 2019 geographies
                   restricted to the agri-food system (regions_agri:
                   2019_raw/2019_FR_agri, 2019_W_agri...), then the outputs
                   stages with the _agri suffix.
    step <name>    a single batch step (see STEPS), e.g. "step engine --suffix _agri".

Each chain stops at the first failing stage. A batch step processes all its
runs even when one fails, so that every failure is reported at once, then
fails if at least one run failed.

The Exiobase version (--version) is written into the generated settings and
passed to the Python scripts through the PLANEFR_EXIOBASE_VERSION environment
variable. update_calib_fr runs from the datapack project (sibling of
matmat-ademe), whose environment holds that pipeline; every other step runs
from matmat-ademe. The settings of each run are generated from the templates
of planeFR/parameters under data/4-PlaneFR/Settings_run (see
_common/planefr_settings.py).

Only depends on the standard library.
"""

import argparse
import os
import posixpath
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent / "_common"))

from planefr_settings import (  # noqa: E402
    Layout,
    add_suffix,
    read_base_year,
    read_template,
    set_last_year_in_path,
    set_version_in_path,
    set_year_in_path,
    write_run_settings,
)

DEFAULT_VERSION = "3.11.2"
BASE_YEARS = (2015, 2019)
AGRI_SUFFIX = "_agri"

# Settings templates, relative to planeFR/parameters
ADAPTER_TEMPLATE = "1-exiobase3_eeio/exiobase3_eeio_settings.json"
GMRIO_FR_TEMPLATE = "2-gmrio_to_snac_s/gmrio_to_snac_S_FR.json"
GMRIO_SSPS_TEMPLATE = "2-gmrio_to_snac_s/gmrio_to_snac_S_SSPs.json"
CALIB_FR_TEMPLATE = "3-update_calib_fr/update_calib_fr_FR.json"
CALIB_SSPS_TEMPLATE = "3-update_calib_fr/update_calib_fr_SSPs.json"
WORLD_ENGINE_TEMPLATE = "4-engine/settings_engine_World.json"
SSP_ENGINE_TEMPLATE = "4-engine/settings_engine_SSPs.json"
FRANCE_ENGINE_TEMPLATE = "4-engine/settings_engine_France_shocks.json"

# Paths of the settings, relative to the data folder of matmat-ademe
PLANEFR_DATA = "./4-PlaneFR"
EXIOBASE_ACCOUNTS = f"{PLANEFR_DATA}/1-accounts/Exiobase"
TRANSITIONS_SHOCKS = f"{PLANEFR_DATA}/2-shocks/1-transitions_2050"
SSP_SHOCKS = f"{PLANEFR_DATA}/2-shocks/3-SSPs_2050"
WORLD_OUTPUTS = f"{PLANEFR_DATA}/Outputs/World"
FRANCE_ACCOUNTS = f"{PLANEFR_DATA}/Outputs/France"
GMRIO_SSPS_OUTPUTS = f"{PLANEFR_DATA}/Outputs_inter/gmrio_to_snac_s/SSPs"

# Python scripts, relative to planeFR/scripts
EXTRACT_F_Y_TOT = "base_accounts/extract_f_y_tot.py"
REFORMAT_MONDE_EUROPE = "outputs/reformat_d_cba_monde_europe.py"
REFORMAT_K = "outputs/reformat_d_cba_k.py"
BUILD_SCENARIO_GROUPS = "outputs/build_scenario_groups.py"
EXPORT_DS = "france_shocks/export_dS.py"
COMPUTE_DS_X_DOM = "france_shocks/compute_ds_x_dom.py"
EXTRACT_S_SSPS = "ssp_shocks/extract_S_SSPs.py"
GENERATE_SHOCK_DS = "ssp_shocks/generate_shock_dS.py"
GENERATE_SHOCK_AGRI = "agri_shocks/generate_shock_agri.py"


# === Display ===
# Stages of a chain are shown as wide banners, the runs of a batch step as
# coloured "=== ... ===" lines, each preceded by a blank line, so that they
# stand out from the output of MatMat. Colours only when writing to a terminal
# (and NO_COLOR is not set).

BOLD, DIM = "1", "2"
RED, GREEN, YELLOW, CYAN = "91", "92", "93", "96"
WHITE_ON_BLUE, WHITE_ON_GREEN, WHITE_ON_RED = "1;97;44", "1;97;42", "1;97;41"
BANNER_WIDTH = 78


def use_color():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        os.system("")  # enables the ANSI sequences in the Windows console
    return True


def style(text, *codes):
    return f"\033[{';'.join(codes)}m{text}\033[0m" if codes and use_color() else text


def banner(text, color):
    """Full-width coloured band on 3 lines (blank band, text, blank band),
    preceded by two blank lines."""
    width = max(BANNER_WIDTH, len(text) + 6)
    bar = style(" " * width, color)
    print(f"\n\n{bar}\n{style(f'  {text}'.ljust(width), color)}\n{bar}\n", flush=True)


FAILURE_PREFIXES = ("ERROR", "Pipeline interrupted", "Cannot run")


def log(message):
    """Prints a message, styled according to its beginning: "=== x ===" (a run
    of a batch step), "--- x ---" (sub-step), "> cmd" (command launched), or an
    error."""
    if message.startswith("==="):
        message = f"\n{style(message, BOLD, YELLOW)}"
    elif message.startswith("---"):
        message = style(message, CYAN)
    elif message.startswith("> "):
        message = style(message, DIM)
    elif message.startswith(FAILURE_PREFIXES) or message.endswith("(see above)"):
        message = style(message, BOLD, RED)
    print(message, flush=True)


def reference_scenario(suffix=""):
    """Reference scenario of a suffix: Base_year_2015 by default, otherwise
    the Base_year<suffix> scenario created by generate_shock_agri.py. It is
    both the accounts folder of the no_SSP group of the France engine and the
    gmrio_to_snac_s output whose F_x_dom are copied into each SSP scenario."""
    return f"Base_year{suffix}" if suffix else "Base_year_2015"


# A runner executes a command in a folder with an environment and returns its
# exit code. The tests replace it with a runner that records the commands.
Runner = Callable[[list, Path, dict], int]


def subprocess_runner(cmd, cwd, env):
    log(f"> {subprocess.list2cmdline(cmd)}    [in {cwd}]")
    try:
        return subprocess.run(cmd, cwd=cwd, env=env).returncode
    except FileNotFoundError as error:
        log(f"Cannot run {cmd[0]}: {error}")
        return 127


class Batch:
    """Failures of a batch step: a failed run does not stop the step, which
    returns exit code 1 at the end if at least one run failed."""

    def __init__(self, name):
        self.name = name
        self.failed = False

    def error(self, message):
        log(f"ERROR: {message}")
        self.failed = True

    def check(self, code, what):
        if code != 0:
            self.error(f"{what} failed (code {code})")
        return code == 0

    def subdirs(self, path):
        """Sub-folders of path, sorted by name; a missing folder is a failure."""
        if not path.is_dir():
            self.error(f"folder not found: {path}")
            return []
        return sorted((p for p in path.iterdir() if p.is_dir()), key=lambda p: p.name.lower())

    def result(self):
        if self.failed:
            log(f"{self.name}: at least one run failed (see above)")
            return 1
        return 0


@dataclass
class Stage:
    name: str
    action: Callable[[], int]


def run_chain(title, stages):
    """Runs the stages in order, stopping at the first that fails. Returns its
    exit code (0 if all succeed)."""
    for number, stage in enumerate(stages, start=1):
        banner(f"STAGE {number}/{len(stages)}  |  {stage.name}", WHITE_ON_BLUE)
        code = stage.action()
        if code != 0:
            banner(f"INTERRUPTED: stage {number}/{len(stages)} '{stage.name}' failed (code {code})",
                   WHITE_ON_RED)
            return code
    banner(f"{title}: completed successfully ({len(stages)} stages)", WHITE_ON_GREEN)
    return 0


@dataclass
class Pipeline:
    layout: Layout
    version: str = DEFAULT_VERSION
    runner: Runner = subprocess_runner
    # Selection of the outputs of the final France engines (chains of outputs,
    # agri and change options): French scenarios and groups, names without suffix
    france: tuple = ()
    row: tuple = ()

    # === Commands ===

    def env(self):
        env = dict(os.environ)
        env["PLANEFR_EXIOBASE_VERSION"] = self.version
        # Each "uv run" uses the environment of its own project (matmat-ademe
        # or datapack), not that of the caller
        env.pop("VIRTUAL_ENV", None)
        return env

    def matmat_cli(self, option, name, settings_path, cwd=None):
        """matmat.cli with a generated settings file: option is -a (adapter),
        -p (pipeline) or -e (engine)."""
        cmd = ["uv", "run", "python", "-m", "matmat.cli", option, name,
               "-st", str(settings_path), "--no_confirm"]
        return self.runner(cmd, cwd or self.layout.matmat_dir, self.env())

    def python_script(self, relative_path, *args):
        """Python script of planeFR/scripts, run from matmat-ademe."""
        cmd = ["uv", "run", "python", str(self.layout.scripts_dir / relative_path),
               *(str(arg) for arg in args)]
        return self.runner(cmd, self.layout.matmat_dir, self.env())

    def _write(self, template, settings):
        return write_run_settings(self.layout, template, settings)

    # === Batch steps ===

    def exiobase3_eeio(self):
        """exiobase3_eeio adapter for each base year, then the World eeio
        engine on these accounts."""
        batch = Batch("exiobase3_eeio")
        v = self.version
        for year in BASE_YEARS:
            log(f"=== exiobase3_eeio: base_year={year} / version={v} ===")
            settings = read_template(self.layout, ADAPTER_TEMPLATE)
            settings["base_year"] = year
            settings["version"] = v
            settings["path_out"] = f"{EXIOBASE_ACCOUNTS}/{v}_{year}"
            path = self._write(ADAPTER_TEMPLATE, settings)
            batch.check(self.matmat_cli("-a", "exiobase3_eeio", path),
                        f"exiobase3_eeio for base_year={year}")

        for year in BASE_YEARS:
            log(f"=== eeio (World): base_year={year} / version={v} ===")
            settings = read_template(self.layout, WORLD_ENGINE_TEMPLATE)
            settings["path_in"]["accounts"] = f"{EXIOBASE_ACCOUNTS}/{v}_{year}/{v}_pxp_{year}"
            settings["path_out"] = f"{WORLD_OUTPUTS}/Base_year_{year}"
            path = self._write(WORLD_ENGINE_TEMPLATE, settings)
            batch.check(self.matmat_cli("-e", "eeio", path), f"World engine for base_year={year}")
        return batch.result()

    def gmrio_to_snac_s(self):
        """gmrio_to_snac_s for each base year."""
        batch = Batch("gmrio_to_snac_s")
        v = self.version
        for year in BASE_YEARS:
            log(f"=== gmrio_to_snac_s: base_year={year} / version={v} ===")
            settings = read_template(self.layout, GMRIO_FR_TEMPLATE)
            path_in = settings["path_in"]
            path_in["accounts"] = set_version_in_path(set_year_in_path(path_in["accounts"], year), v)
            settings["path_out"] = set_version_in_path(set_year_in_path(settings["path_out"], year), v)
            path = self._write(GMRIO_FR_TEMPLATE, settings)
            batch.check(self.matmat_cli("-p", "gmrio_to_snac_s", path),
                        f"gmrio_to_snac_s for base_year={year}")
        return batch.result()

    def gmrio_to_snac_s_ssps(self, suffix="", reference=None):
        """gmrio_to_snac_s on the World accounts of each scenario of
        3-SSPs_2050<suffix>, then replaces their F_x_dom by those of the
        reference output (the French domestic intensities are not changed by
        an SSP scenario). The reference is processed first."""
        reference = reference or reference_scenario(suffix)
        batch = Batch(f"gmrio_to_snac_s SSPs{suffix}")
        template = read_template(self.layout, GMRIO_SSPS_TEMPLATE)
        # ".../Outputs/World/<scenario>" and ".../SSPs/<scenario>": parent folders
        accounts_base = posixpath.dirname(template["path_in"]["accounts"])
        out_base = re.sub(f"{AGRI_SUFFIX}$", "", posixpath.dirname(template["path_out"])) + suffix

        scenarios = [d.name for d in batch.subdirs(self.layout.data_path(f"{SSP_SHOCKS}{suffix}"))]
        scenarios.sort(key=lambda name: (add_suffix(name, suffix) != reference, name.lower()))

        for scenario in scenarios:
            name = add_suffix(scenario, suffix)
            log(f"=== gmrio_to_snac_s: {scenario} ===")
            settings = read_template(self.layout, GMRIO_SSPS_TEMPLATE)
            settings["path_in"]["accounts"] = posixpath.join(accounts_base, name)
            settings["path_out"] = posixpath.join(out_base, name)
            path = self._write(GMRIO_SSPS_TEMPLATE, settings)
            if not batch.check(self.matmat_cli("-p", "gmrio_to_snac_s", path),
                               f"gmrio_to_snac_s for {scenario}"):
                continue
            if name == reference:
                continue

            ref_dir = self.layout.data_path(posixpath.join(out_base, reference))
            scenario_out = self.layout.data_path(posixpath.join(out_base, name))
            log(f"--- {scenario}: F_x_dom replaced by those of {ref_dir} ---")
            for ext in template["extension_names"]:
                src = ref_dir / "extensions" / f"dom_{ext}" / "F_x_dom.pkl"
                dst = scenario_out / "extensions" / f"dom_{ext}" / "F_x_dom.pkl"
                if not src.is_file():
                    batch.error(f"reference F_x_dom not found: {src}")
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        return batch.result()

    def _check_datapack(self, batch):
        if not self.layout.datapack_dir.is_dir():
            batch.error(f"datapack project not found: {self.layout.datapack_dir} "
                        "(it holds the update_calib_fr pipeline)")
            return False
        return True

    def update_calib_fr(self):
        """update_calib_fr for each base year: adds the new extensions to the
        France calibration. Only the newer_accounts path takes the version;
        older_accounts (France calibration, 3.10.2) is not changed."""
        batch = Batch("update_calib_fr")
        if not self._check_datapack(batch):
            return batch.result()
        for year in BASE_YEARS:
            log(f"=== update_calib_fr: base_year={year} ===")
            settings = read_template(self.layout, CALIB_FR_TEMPLATE)
            path_in = settings["path_in"]
            path_in["newer_accounts"] = set_version_in_path(
                set_last_year_in_path(path_in["newer_accounts"], year), self.version)
            path_in["older_accounts"] = set_last_year_in_path(path_in["older_accounts"], year)
            settings["path_out"] = set_last_year_in_path(settings["path_out"], year)
            path = self._write(CALIB_FR_TEMPLATE, settings)
            batch.check(self.matmat_cli("-p", "update_calib_fr", path, cwd=self.layout.datapack_dir),
                        f"update_calib_fr for base_year={year}")
        return batch.result()

    def _newer_accounts_subdir(self, scenario_dir):
        """Sub-folder of a gmrio_to_snac_s output holding its accounts: "" if
        system/ is directly in it (e.g. Base_year_2015), otherwise its
        <version>_pxp_<year> sub-folder (e.g. SSP1_2050/3.11.2_pxp_2019);
        None if there is none."""
        if (scenario_dir / "system" / "info.json").is_file():
            return ""
        for sub in sorted(scenario_dir.glob(f"{self.version}_pxp_*")):
            if (sub / "system" / "info.json").is_file():
                return sub.name
        return None

    def update_calib_fr_ssps(self, suffix=""):
        """update_calib_fr for each gmrio_to_snac_s output of SSPs<suffix>,
        written to Outputs/France<suffix>/<scenario>; older_accounts takes the
        base_year of the scenario."""
        batch = Batch(f"update_calib_fr SSPs{suffix}")
        if not self._check_datapack(batch):
            return batch.result()
        newer_base = f"{GMRIO_SSPS_OUTPUTS}{suffix}"
        out_base = f"{FRANCE_ACCOUNTS}{suffix}"

        for scenario_dir in batch.subdirs(self.layout.data_path(newer_base)):
            scenario = scenario_dir.name
            sub = self._newer_accounts_subdir(scenario_dir)
            if sub is None:
                log(f"Scenario {scenario} skipped: no system/info.json "
                    f"(nor in a {self.version}_pxp_* sub-folder)")
                continue
            newer_accounts = posixpath.join(newer_base, scenario, sub) if sub else posixpath.join(newer_base, scenario)
            base_year = read_base_year(self.layout.data_path(newer_accounts))
            log(f"=== update_calib_fr: {scenario} (base_year={base_year}) ===")

            settings = read_template(self.layout, CALIB_SSPS_TEMPLATE)
            path_in = settings["path_in"]
            path_in["newer_accounts"] = newer_accounts
            path_in["older_accounts"] = set_last_year_in_path(path_in["older_accounts"], base_year)
            settings["path_out"] = posixpath.join(out_base, scenario)
            path = self._write(CALIB_SSPS_TEMPLATE, settings)
            batch.check(self.matmat_cli("-p", "update_calib_fr", path, cwd=self.layout.datapack_dir),
                        f"update_calib_fr for {scenario}")
        return batch.result()

    def engine_ssps(self, suffix=""):
        """World eeio engine, one run per scenario of 3-SSPs_2050<suffix>.
        path_in.accounts of the template (base World accounts of the SSP
        shocks, see planefr_paths.get_ssp_base_accounts_dir) is kept as is."""
        batch = Batch(f"World engine SSPs{suffix}")
        out_base = posixpath.dirname(read_template(self.layout, SSP_ENGINE_TEMPLATE)["path_out"])

        for scenario_dir in batch.subdirs(self.layout.data_path(f"{SSP_SHOCKS}{suffix}")):
            scenario = scenario_dir.name
            log(f"=== eeio (World): {scenario} ===")
            settings = read_template(self.layout, SSP_ENGINE_TEMPLATE)
            settings["path_in"]["shock"] = f"{SSP_SHOCKS}{suffix}/{scenario}"
            settings["path_out"] = posixpath.join(out_base, add_suffix(scenario, suffix))
            path = self._write(SSP_ENGINE_TEMPLATE, settings)
            batch.check(self.matmat_cli("-e", "eeio", path), f"World engine for {scenario}")
        return batch.result()

    def engine(self, suffix="", no_ssp_only=False, ssps_only=False, france=(), row=()):
        """France eeio engine: the 2015 and 2019 baselines (without suffix),
        then one run per pair (accounts folder of Outputs/France<suffix>
        except 2019, scenario of 1-transitions_2050<suffix>). Outputs in
        Module_PlaneFR/data/Outputs_MatMat/<version>/2050_raw/<group>/<scenario>
        (2019_FR in <version>/2019_raw/), <group> being
        no_SSP<suffix> for the reference accounts and the accounts folder name
        otherwise. The reference baseline (no_SSP<suffix>/<reference>) is
        copied into each other group.

        no_ssp_only: only the no_SSP<suffix> group (reference accounts and
        their baseline), i.e. the runs read by export_dS.py.
        ssps_only: every group except no_SSP<suffix> (the SSP groups); the
        baselines are not recomputed, the copied reference baseline is that
        of a previous run.
        france, row: only the outputs of these French scenarios (e.g.
        S1_2050) and of these groups (no_SSP, or an SSP such as SSP2_2050),
        names without suffix; the pairs are the combinations of both lists
        (all the scenarios / all the groups if empty). The baselines are then
        not recomputed."""
        label = " (no_SSP only)" if no_ssp_only else " (SSP groups only)" if ssps_only else ""
        if france or row:
            label += f" [{' '.join(france) or 'all'} x {' '.join(row) or 'all'}]"
        batch = Batch(f"France engine{suffix}{label}")
        module_dir = self.layout.module_dir
        if module_dir is None or not module_dir.is_dir():
            batch.error(f"Module_PlaneFR folder not found: {module_dir} (set PLANEFR_MODULE_DIR)")
            return batch.result()
        version_dir = module_dir.resolve() / "data" / "Outputs_MatMat" / self.version
        out_base = version_dir / "2050_raw"
        out_2019 = version_dir / "2019_raw"
        accounts_base = f"{FRANCE_ACCOUNTS}{suffix}"
        shocks_base = f"{TRANSITIONS_SHOCKS}{suffix}"
        # Accounts folder of the no_SSP group, and baseline scenario copied
        # into the other groups as the reference of the figures
        reference = reference_scenario(suffix)
        no_ssp_group = f"no_SSP{suffix}"

        def group_of(accounts_name):
            return no_ssp_group if accounts_name == reference else add_suffix(accounts_name, suffix)

        def run(accounts, shock, path_out, label):
            log(f"=== eeio (France): {label} ===")
            settings = read_template(self.layout, FRANCE_ENGINE_TEMPLATE)
            settings["path_in"]["accounts"] = accounts
            settings["path_in"]["shock"] = shock
            settings["path_out"] = path_out.as_posix()
            path = self._write(FRANCE_ENGINE_TEMPLATE, settings)
            batch.check(self.matmat_cli("-e", "eeio", path), f"France engine for {label}")

        scenarios = [d.name for d in batch.subdirs(self.layout.data_path(shocks_base))]
        # Reference accounts first: their baseline is copied into the next groups
        accounts_names = sorted(
            (d.name for d in batch.subdirs(self.layout.data_path(accounts_base)) if "2019" not in d.name),
            key=lambda name: (name != reference, name.lower()),
        )
        if no_ssp_only:
            if reference not in accounts_names:
                batch.error(f"reference accounts {reference} not found in {self.layout.data_path(accounts_base)}")
            accounts_names = [name for name in accounts_names if name == reference]
        elif ssps_only:
            accounts_names = [name for name in accounts_names if name != reference]
            if not accounts_names:
                batch.error(f"no SSP accounts in {self.layout.data_path(accounts_base)} (run ssp-shocks first)")

        # Selection of outputs: unknown names are reported with the available ones
        if row:
            wanted = {add_suffix(name, suffix) for name in row}
            available = sorted({group_of(name) for name in accounts_names})
            unknown = sorted(wanted - set(available))
            if unknown:
                batch.error(f"unknown RoW scenario(s): {', '.join(unknown)} (available: {', '.join(available)})")
            accounts_names = [name for name in accounts_names if group_of(name) in wanted]
        if france:
            wanted = {add_suffix(name, suffix) for name in france}
            # Shock folders of a suffixed set may or may not carry the suffix
            available = sorted({add_suffix(name, suffix) for name in scenarios})
            unknown = sorted(wanted - set(available))
            if unknown:
                batch.error(f"unknown French scenario(s): {', '.join(unknown)} "
                            f"(available: {', '.join(available)})")
            scenarios = [name for name in scenarios if add_suffix(name, suffix) in wanted]

        # Baselines without shock (not recomputed with a suffix or a selection)
        for year in () if suffix or ssps_only or france or row else BASE_YEARS:
            name = f"Base_year_{year}"
            if no_ssp_only and name != reference:
                continue
            if year == 2019:
                path_out = out_2019 / "2019_FR"
            elif name == reference:
                path_out = out_base / no_ssp_group / name
            else:
                path_out = out_base / name
            run(f"{accounts_base}/{name}", None, path_out, f"baseline {name}")

        for accounts_name in accounts_names:
            group = group_of(accounts_name)
            for scenario in scenarios:
                # The reference baseline of the other groups is a copy (below)
                if scenario == reference and accounts_name != reference:
                    continue
                run(f"{accounts_base}/{accounts_name}", f"{shocks_base}/{scenario}",
                    out_base / group / add_suffix(scenario, suffix), f"{accounts_name} / {scenario}")

            if accounts_name == reference:
                continue
            baseline = out_base / no_ssp_group / reference
            group_copy = out_base / group / reference
            if not (baseline / "extensions").is_dir():
                batch.error(f"cannot copy {reference} into {group}: {baseline} not found or incomplete")
                continue
            log(f"--- {group}: copy of {baseline} ---")
            if group_copy.exists():
                shutil.rmtree(group_copy)
            shutil.copytree(baseline, group_copy)
        return batch.result()

    def regions_agri(self, suffix=AGRI_SUFFIX):
        """2019 geographies restricted to the agri-food system (REGIONS<suffix>
        group of the figures), from the Base_year<suffix> shocks written by
        generate_shock_agri.py (dS = 0 on the Food sectors, -1 elsewhere):

        1. World engine on the World 2019 output with the Base_year<suffix>
           shock of 3-SSPs_2050<suffix> -> Outputs/World/Base_year_2019<suffix>,
           turned into 2019_raw/2019_W<suffix>, 2019_EU27<suffix>,
           2019_<code><suffix> by reformat_d_cba_monde_europe.py;
        2. gmrio_to_snac_s then update_calib_fr (France calibration 2019) on it
           -> Outputs/France<suffix>/Base_year_2019<suffix> (ignored by the
           France engine of the 2050 groups, whose accounts exclude "2019");
        3. France engine on these accounts with the Base_year<suffix> shock of
           1-transitions_2050<suffix> (it also filters the extensions coming
           from the older France calibration) -> 2019_raw/2019_FR<suffix>.

        Both shocks only depend on the sector labels, identical for the 2015
        and 2019 accounts. The runs depend on each other: the step stops at
        the first failure."""
        batch = Batch(f"2019 regions{suffix}")
        module_dir = self.layout.module_dir
        if module_dir is None or not module_dir.is_dir():
            batch.error(f"Module_PlaneFR folder not found: {module_dir} (set PLANEFR_MODULE_DIR)")
            return batch.result()
        reference = reference_scenario(suffix)
        name = f"Base_year_2019{suffix}"
        world_out = f"{WORLD_OUTPUTS}/{name}"
        gmrio_out = posixpath.join(posixpath.dirname(GMRIO_SSPS_OUTPUTS), name)
        france_accounts = f"{FRANCE_ACCOUNTS}{suffix}/{name}"
        out_2019 = module_dir.resolve() / "data" / "Outputs_MatMat" / self.version / "2019_raw"

        for shock in (f"{SSP_SHOCKS}{suffix}/{reference}", f"{TRANSITIONS_SHOCKS}{suffix}/{reference}"):
            if not self.layout.data_path(shock).is_dir():
                batch.error(f"shock not found: {self.layout.data_path(shock)} (run generate_shock_agri.py first)")
        if batch.failed:
            return batch.result()

        log(f"=== eeio (World): {name} ===")
        settings = read_template(self.layout, WORLD_ENGINE_TEMPLATE)
        settings["path_in"]["accounts"] = f"{WORLD_OUTPUTS}/Base_year_2019"
        settings["path_in"]["shock"] = f"{SSP_SHOCKS}{suffix}/{reference}"
        settings["path_out"] = world_out
        if not batch.check(self.matmat_cli("-e", "eeio", self._write(WORLD_ENGINE_TEMPLATE, settings)),
                           f"World engine for {name}"):
            return batch.result()

        log(f"=== gmrio_to_snac_s: {name} ===")
        settings = read_template(self.layout, GMRIO_SSPS_TEMPLATE)
        settings["path_in"]["accounts"] = world_out
        settings["path_out"] = gmrio_out
        if not batch.check(self.matmat_cli("-p", "gmrio_to_snac_s", self._write(GMRIO_SSPS_TEMPLATE, settings)),
                           f"gmrio_to_snac_s for {name}"):
            return batch.result()

        log(f"=== update_calib_fr: {name} (base_year=2019) ===")
        if not self._check_datapack(batch):
            return batch.result()
        sub = self._newer_accounts_subdir(self.layout.data_path(gmrio_out))
        settings = read_template(self.layout, CALIB_SSPS_TEMPLATE)
        settings["path_in"]["newer_accounts"] = posixpath.join(gmrio_out, sub) if sub else gmrio_out
        settings["path_in"]["older_accounts"] = set_last_year_in_path(settings["path_in"]["older_accounts"], 2019)
        settings["path_out"] = france_accounts
        if not batch.check(self.matmat_cli("-p", "update_calib_fr", self._write(CALIB_SSPS_TEMPLATE, settings),
                                           cwd=self.layout.datapack_dir), f"update_calib_fr for {name}"):
            return batch.result()

        log(f"=== eeio (France): 2019_FR{suffix} ===")
        settings = read_template(self.layout, FRANCE_ENGINE_TEMPLATE)
        settings["path_in"]["accounts"] = france_accounts
        settings["path_in"]["shock"] = f"{TRANSITIONS_SHOCKS}{suffix}/{reference}"
        settings["path_out"] = (out_2019 / f"2019_FR{suffix}").as_posix()
        batch.check(self.matmat_cli("-e", "eeio", self._write(FRANCE_ENGINE_TEMPLATE, settings)),
                    f"France engine for 2019_FR{suffix}")
        return batch.result()

    # === Chains ===

    def _script(self, name, script, *args):
        return Stage(name, lambda: self.python_script(script, *args))

    def _reformat_stages(self):
        """Post-processing of the France engine outputs. reformat_d_cba_monde_europe
        resets F_Y_tot to its base-year value in ALL the scenario folders: the
        F_Y_tot shocks must be reapplied after it (compute_ds_x_dom.py)."""
        return [
            self._script("outputs: reformat_d_cba_monde_europe", REFORMAT_MONDE_EUROPE),
            self._script("outputs: reformat_d_cba_k", REFORMAT_K),
        ]

    def _base_accounts_stages(self):
        """Accounts that only depend on Exiobase and the France calibration
        (rerun by --All only, e.g. after a change of --version)."""
        return [
            Stage("1-exiobase3_eeio: adapter and World engine", self.exiobase3_eeio),
            self._script("base_accounts: extract_f_y_tot", EXTRACT_F_Y_TOT),
            Stage("2-gmrio_to_snac_s: France SNAC accounts", self.gmrio_to_snac_s),
            Stage("3-update_calib_fr: France calibration", self.update_calib_fr),
        ]

    def _projected_world_stages(self, suffix=""):
        """Rest of the world projected on each SSP shock of 3-SSPs_2050<suffix>,
        down to the France accounts Outputs/France<suffix>/<SSP>."""
        s = suffix
        return [
            Stage(f"4-engine: World engine SSPs{s}", lambda: self.engine_ssps(s)),
            Stage(f"2-gmrio_to_snac_s: SSPs{s}", lambda: self.gmrio_to_snac_s_ssps(s)),
            Stage(f"3-update_calib_fr: SSPs{s}", lambda: self.update_calib_fr_ssps(s)),
        ]

    def chain_france_shocks(self, manual_only=False):
        # export_dS reads the 2050 production x of the no_SSP group and the
        # base-year F_x_dom / F_Y_tot (the latter two written by the reformat scripts).
        # x does not depend on the dS_x_dom applied by the engine: the
        # dS_x_dom computed here are exact after a single pass.
        # manual_only: only my_manual_param.xlsx has changed, so x and
        # S_extraction.xlsx are still valid: compute_ds_x_dom alone suffices.
        if manual_only:
            return [self._script("france_shocks: compute_ds_x_dom", COMPUTE_DS_X_DOM)]
        return [
            Stage("4-engine: France engine (no_SSP)", lambda: self.engine(no_ssp_only=True)),
            *self._reformat_stages(),
            self._script("france_shocks: export_dS", EXPORT_DS),
            self._script("france_shocks: compute_ds_x_dom", COMPUTE_DS_X_DOM),
        ]

    def chain_ssp_shocks(self):
        return [
            self._script("ssp_shocks: extract_S_SSPs", EXTRACT_S_SSPS),
            self._script("ssp_shocks: generate_shock_dS", GENERATE_SHOCK_DS),
            *self._projected_world_stages(),
        ]

    def _france_engine_stage(self, suffix="", ssps_only=False):
        # ssps_only: France engine on the SSP groups only (no_SSP unchanged)
        label = " (SSP groups)" if ssps_only else ""
        return Stage(f"4-engine: France engine{suffix}{label}",
                     lambda: self.engine(suffix, ssps_only=ssps_only, france=self.france, row=self.row))

    def _post_outputs_stages(self):
        # Every scenario folder, "_agri" or not: run once after all the France
        # engines. The dS_x_dom are those of the last france-shocks run:
        # compute_ds_x_dom only reapplies the F_Y_tot shocks reset by the reformat scripts.
        return [
            *self._reformat_stages(),
            self._script("france_shocks: compute_ds_x_dom (F_Y_tot)", COMPUTE_DS_X_DOM, "--only-f-y-tot"),
            self._script("outputs: build_scenario_groups", BUILD_SCENARIO_GROUPS),
        ]

    def _agri_shocks_stage(self, only=None):
        """generate_shock_agri.py, restricted to some shock sets (transitions,
        ssps) if only is given: the other _agri set is left untouched."""
        args = ["--only", *only] if only else []
        label = f" ({', '.join(only)})" if only else ""
        return self._script(f"agri_shocks: generate_shock_agri{label}", GENERATE_SHOCK_AGRI, *args)

    def chain_outputs(self, suffix="", ssps_only=False):
        return [self._france_engine_stage(suffix, ssps_only), *self._post_outputs_stages()]

    def _regions_agri_stages(self):
        """2019 geographies of the agri-food variant (regions_agri), unless the
        run is restricted to some outputs (--France / --RoW), which, like the
        baselines, they are not part of."""
        if self.france or self.row:
            return []
        return [Stage(f"4-engine: 2019 regions{AGRI_SUFFIX}", self.regions_agri)]

    def chain_agri(self):
        # generate_shock_agri.py derives the _agri shocks from 1-transitions_2050
        # and 3-SSPs_2050: run france-shocks / ssp-shocks first if they changed.
        s = AGRI_SUFFIX
        return [
            self._agri_shocks_stage(),
            *self._projected_world_stages(s),
            *self._regions_agri_stages(),
            *self.chain_outputs(s),
        ]

    def chain_change(self, changes=(), agri=False):
        """Chains matching one or several types of change (CHANGE_HELP),
        optionally with the agri-food variant. Each shock chain concerned runs
        once, then a single France engine pass and a single post-processing
        (reformat scripts, F_Y_tot, build_scenario_groups):
        - French shocks only: France engine on every group; with agri, only
          1-transitions_2050_agri is rebuilt and the _agri projected world
          (which only depends on the SSP shocks) is not rerun;
        - SSP shocks only: both France engines only run the SSP groups; with
          agri, only 3-SSPs_2050_agri is rebuilt;
        - French and SSP shocks (or All): everything after the shocks.
        France_shocks_change includes France_shocks_dS_change. Without a
        change, agri alone: the agri chain."""
        changes = {changes} if isinstance(changes, str) else set(changes)
        if not changes:
            return self.chain_agri()
        everything = "All" in changes
        france = everything or bool(changes & {"France_shocks_change", "France_shocks_dS_change"})
        manual_only = not everything and "France_shocks_change" not in changes
        row = everything or "RoW_shocks_change" in changes

        stages = self._base_accounts_stages() if everything else []
        if france:
            stages += self.chain_france_shocks(manual_only=manual_only)
        if row:
            stages += self.chain_ssp_shocks()
        ssps_only = not france
        engines = [self._france_engine_stage("", ssps_only)]
        if agri:
            s = AGRI_SUFFIX
            only = None if france and row else ["transitions"] if france else ["ssps"]
            stages.append(self._agri_shocks_stage(only))
            if row:
                stages += self._projected_world_stages(s)
            # Base_year_agri shocks regenerated: the 2019 agri geographies follow
            stages += self._regions_agri_stages()
            engines.append(self._france_engine_stage(s, ssps_only))
        return stages + engines + self._post_outputs_stages()


# Shortcuts by type of change (Pipeline.chain_change); --Agri can be added to any
CHANGE_HELP = {
    "All": "everything (e.g. Exiobase version or France calibration changed): base accounts, "
           "then france-shocks, ssp-shocks and outputs",
    "RoW_shocks_change": "SSP shocks changed (IMAGE scenarios, Matching workbook): ssp-shocks, then outputs --ssps",
    "France_shocks_change": "system shocks of 1-transitions_2050 changed: france-shocks, then outputs",
    "France_shocks_dS_change": "my_manual_param.xlsx changed only: france-shocks --manual-only, then outputs",
}
AGRI_HELP = ("agri-food variant. Alone: _agri shocks from the current France and SSP shocks, rest of the "
             "world projected on them, then the outputs stages with the _agri suffix (agri). With one of "
             "the options above: only the _agri part affected by the change is recomputed, and the "
             "post-processing runs once for both variants")


# Batch steps runnable alone ("step <name>"), and whether they take --suffix
STEPS = {
    "exiobase3_eeio": (lambda p, a: p.exiobase3_eeio(), False),
    "gmrio_to_snac_s": (lambda p, a: p.gmrio_to_snac_s(), False),
    "gmrio_to_snac_s_ssps": (lambda p, a: p.gmrio_to_snac_s_ssps(a.suffix, a.reference), True),
    "update_calib_fr": (lambda p, a: p.update_calib_fr(), False),
    "update_calib_fr_ssps": (lambda p, a: p.update_calib_fr_ssps(a.suffix), True),
    "engine": (lambda p, a: p.engine(a.suffix), True),
    "engine_no_ssp": (lambda p, a: p.engine(a.suffix, no_ssp_only=True), True),
    "engine_ssps": (lambda p, a: p.engine_ssps(a.suffix), True),
    "regions_agri": (lambda p, a: p.regions_agri(), False),
}


def list_scenarios(layout):
    """(French scenarios, groups) existing on disk, for --help: the scenarios of
    1-transitions_2050, and no_SSP plus the scenarios of 3-SSPs_2050 (RoW).
    Empty lists if the shocks are not generated yet."""
    def names(path):
        folder = layout.data_path(path)
        return sorted(d.name for d in folder.iterdir() if d.is_dir()) if folder.is_dir() else []

    reference = reference_scenario()
    france = [name for name in names(TRANSITIONS_SHOCKS) if name != reference]
    row = ["no_SSP"] + [name for name in names(SSP_SHOCKS) if name != reference]
    return france, row


def selection_help(layout):
    try:
        france, row = list_scenarios(layout or Layout.default())
    except Exception:  # Module_PlaneFR not found...: help without the lists
        france, row = [], []
    return ("Outputs that can be selected with --France / --RoW (names without the _agri suffix):\n"
            f"  French scenarios (--France): {', '.join(france) or '(none found)'}\n"
            f"  RoW scenarios    (--RoW):    {', '.join(row) or '(none found)'}")


ONLY_FRANCE_HELP = ("only the outputs of these French scenarios (e.g. S1_2050); the outputs generated are "
                    "the combinations with --RoW (all if omitted). The baselines (Base_year_2015, "
                    "2019_FR) are then not recomputed")
ONLY_ROW_HELP = ("only the outputs of these RoW scenarios: no_SSP (base-year accounts) or an SSP (e.g. "
                 "SSP2_2050); combined with --France (all if omitted)")


def add_selection_options(parser, dest_prefix=""):
    parser.add_argument("--France", dest=f"{dest_prefix}france", nargs="+", metavar="SCENARIO",
                        default=[], help=ONLY_FRANCE_HELP)
    parser.add_argument("--RoW", dest=f"{dest_prefix}row", nargs="+", metavar="SCENARIO",
                        default=[], help=ONLY_ROW_HELP)


def build_parser(layout=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--version", default=DEFAULT_VERSION,
                        help=f"Exiobase version (default {DEFAULT_VERSION})")
    # Subcommand copy of the selection (distinct dest: a sub-parser default
    # would overwrite the value parsed before the command)
    selection = argparse.ArgumentParser(add_help=False)
    add_selection_options(selection, "cmd_")

    parser = argparse.ArgumentParser(
        prog="planefr.py",
        description="PlaneFR pipeline in matmat-ademe (see the docstring of this file). "
                    "Either a type of change (--All...) or a command.",
        epilog=selection_help(layout),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    changes = parser.add_argument_group(
        "what has changed (runs the matching chains; several can be combined, "
        "e.g. --France_shocks_change --RoW_shocks_change)")
    for name, help_text in CHANGE_HELP.items():
        changes.add_argument(f"--{name}", dest="changes", action="append_const", const=name, help=help_text)
    changes.add_argument("--Agri", dest="agri", action="store_true", help=AGRI_HELP)
    add_selection_options(changes)
    changes.add_argument("--version", dest="change_version", default=DEFAULT_VERSION,
                         help=f"Exiobase version, with a type of change (default {DEFAULT_VERSION})")
    commands = parser.add_subparsers(dest="command", metavar="command")
    france = commands.add_parser("france-shocks", parents=[common],
                                 help="regenerate the French shocks (e.g. after editing my_manual_param.xlsx)")
    france.add_argument("--manual-only", action="store_true",
                        help="only my_manual_param.xlsx has changed (not the system shocks, accounts "
                             "or version): skip the engine and only run compute_ds_x_dom")
    commands.add_parser("ssp-shocks", parents=[common],
                        help="regenerate the SSP shocks and the rest of the world projected on them")
    outputs = commands.add_parser("outputs", parents=[common, selection],
                                  help="all the output groups (no_SSP, SSP2_2050...) from the current shocks")
    outputs.add_argument("--ssps", action="store_true",
                         help="only the SSP groups (every accounts folder except no_SSP), e.g. after "
                              "ssp-shocks; no_SSP and 2019_FR are not recomputed")
    commands.add_parser("agri", parents=[common, selection],
                        help="agri-food variant of outputs (regenerates the _agri shocks first)")
    step = commands.add_parser("step", parents=[common], help="a single batch step")
    step.add_argument("name", choices=list(STEPS))
    step.add_argument("--suffix", default="",
                      help=f"suffix of the shock, accounts and output folders (e.g. {AGRI_SUFFIX})")
    step.add_argument("--reference", default=None,
                      help="gmrio_to_snac_s_ssps: output whose F_x_dom are copied into each "
                           "scenario (default Base_year_2015, or Base_year<suffix>)")
    return parser


def main(argv=None, layout=None, runner=subprocess_runner):
    layout = layout or Layout.default()
    parser = build_parser(layout)
    args = parser.parse_args(argv)
    changes = list(dict.fromkeys(args.changes or []))
    by_change = bool(changes or args.agri)
    if by_change == bool(args.command):
        parser.error("give either a type of change (e.g. --RoW_shocks_change, --Agri) or a command (e.g. outputs)")
    version = args.change_version if by_change else args.version
    france = tuple(args.france or getattr(args, "cmd_france", []))
    row = tuple(args.row or getattr(args, "cmd_row", []))
    if (france or row) and not by_change and args.command not in ("outputs", "agri"):
        parser.error("--France / --RoW only apply to the outputs and agri commands "
                     "and to the type-of-change options")
    pipeline = Pipeline(layout, version, runner, france=france, row=row)

    chains = {
        "france-shocks": pipeline.chain_france_shocks,
        "france-shocks --manual-only": lambda: pipeline.chain_france_shocks(manual_only=True),
        "ssp-shocks": pipeline.chain_ssp_shocks,
        "outputs": pipeline.chain_outputs,
        "outputs --ssps": lambda: pipeline.chain_outputs(ssps_only=True),
        "agri": pipeline.chain_agri,
    }

    if by_change:
        title = " ".join(f"--{name}" for name in changes + (["Agri"] if args.agri else []))
        return run_chain(f"{title} (version {version})", pipeline.chain_change(changes, args.agri))

    if args.command == "step":
        action, takes_suffix = STEPS[args.name]
        if args.suffix and not takes_suffix:
            parser.error(f"step {args.name} does not take --suffix")
        if args.reference and args.name != "gmrio_to_snac_s_ssps":
            parser.error("--reference only applies to gmrio_to_snac_s_ssps")
        return run_chain(f"step {args.name}", [Stage(args.name, lambda: action(pipeline, args))])

    name = args.command
    if name == "france-shocks" and args.manual_only:
        name = "france-shocks --manual-only"
    elif name == "outputs" and args.ssps:
        name = "outputs --ssps"
    return run_chain(f"{name} (version {version})", chains[name]())


if __name__ == "__main__":
    sys.exit(main())
