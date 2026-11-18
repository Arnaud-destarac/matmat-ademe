"""
Settings templates and path helpers of the PlaneFR pipeline (planeFR/scripts/planefr.py).

The JSON files of planeFR/parameters are TEMPLATES: the pipeline never
modifies them. Each run reads a template (read_template), changes the paths of
that run, then writes the result under data/4-PlaneFR/Settings_run with the
same relative path (write_run_settings): that generated file is passed to
matmat.cli.

In the templates, "{parameters}" stands for the planeFR/parameters folder; it
is replaced by its absolute path in the generated file. The other paths
(accounts, shocks, outputs) stay relative to the data_dir of config.toml,
against which MatMat resolves them with Path(data_dir).joinpath(value).

All the paths of the settings are handled with "/" separators: the templates
may use Windows separators (".\\4-PlaneFR\\..."), which read_template converts,
so that the generated files work on Windows and Linux alike.

Only depends on the standard library: the pipeline can be driven by any
Python interpreter.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

PARAMETERS_TOKEN = "{parameters}"
# Fields of the settings holding paths (as in matmat.workflows.identity)
PATH_FIELDS_PREFIX = "path_"


@dataclass(frozen=True)
class Layout:
    """Folders used by the pipeline. Layout.default() takes them from
    planefr_paths.py; the tests build one on a temporary folder."""

    # matmat-ademe folder
    matmat_dir: Path
    # Module_PlaneFR folder (only needed by the France engine step)
    module_dir: Path | None = None

    @classmethod
    def default(cls):
        # Imported here: planefr_paths checks at import that Module_PlaneFR
        # exists, which the tests do not need
        import planefr_paths

        return cls(matmat_dir=planefr_paths.MATMAT_DIR, module_dir=planefr_paths.MODULE_PLANEFR_DIR)

    @property
    def scripts_dir(self):
        return self.matmat_dir / "planeFR" / "scripts"

    @property
    def parameters_dir(self):
        return self.matmat_dir / "planeFR" / "parameters"

    @property
    def data_dir(self):
        """Data folder of matmat-ademe: data_dir of config.toml, against which
        the relative paths of the settings are resolved."""
        return self.matmat_dir / "data"

    @property
    def run_settings_dir(self):
        return self.data_dir / "4-PlaneFR" / "Settings_run"

    @property
    def datapack_dir(self):
        """datapack project (sibling of matmat-ademe), whose environment holds
        the update_calib_fr pipeline."""
        return self.matmat_dir.parent / "datapack"

    def data_path(self, settings_path):
        """Absolute path of a path of the settings (relative to data_dir)."""
        return self.data_dir / settings_path


# === Paths of the settings ===

def to_posix(path):
    """Settings path with "/" separators (None is kept)."""
    if path is None:
        return None
    return str(path).replace("\\", "/")


def _map_paths(value, func):
    """Applies func to a path field: a string, or the strings of a dict/list
    (e.g. path_in = {"accounts": ..., "bridges": ...})."""
    if isinstance(value, str):
        return func(value)
    if isinstance(value, dict):
        return {key: _map_paths(item, func) for key, item in value.items()}
    if isinstance(value, list):
        return [_map_paths(item, func) for item in value]
    return value


def set_year_in_path(path, year):
    """Replaces every "_20xx" (year) by "_<year>", so that a <version>_<year>
    folder and its <version>_pxp_<year> sub-folder stay consistent."""
    return re.sub(r"_20\d{2}", f"_{year}", path)


def set_last_year_in_path(path, year):
    """Replaces only the last "_20xx" (year) by "_<year>", leaving the rest of
    the path (version, sub-folders) unchanged."""
    return re.sub(r"_20\d{2}(?!.*_20\d{2})", f"_{year}", path)


def set_version_in_path(path, version):
    """Replaces every Exiobase version number (e.g. 3.10.2) by version."""
    return re.sub(r"\d+\.\d+\.\d+", lambda _: version, path)


def add_suffix(name, suffix):
    """Appends suffix to name unless it already ends with it."""
    if not suffix or name.endswith(suffix):
        return name
    return f"{name}{suffix}"


# === Templates ===

def read_template(layout, relative_path):
    """Template planeFR/parameters/<relative_path> (e.g.
    "4-engine/settings_engine_SSPs.json"), its paths with "/" separators."""
    text = (layout.parameters_dir / relative_path).read_text(encoding="utf-8-sig")
    settings = json.loads(text)
    for field, value in settings.items():
        if field.startswith(PATH_FIELDS_PREFIX):
            settings[field] = _map_paths(value, to_posix)
    return settings


def write_run_settings(layout, relative_path, settings):
    """Writes the settings of a run under Settings_run/<relative_path> (same
    relative path as the template it comes from), after replacing
    "{parameters}" by the absolute path of planeFR/parameters. Returns the path
    of the generated file."""
    parameters_dir = layout.parameters_dir.resolve().as_posix()
    settings = dict(settings)
    for field, value in settings.items():
        if field.startswith(PATH_FIELDS_PREFIX):
            settings[field] = _map_paths(
                value, lambda path: to_posix(path).replace(PARAMETERS_TOKEN, parameters_dir)
            )
    run_path = layout.run_settings_dir / relative_path
    run_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 without BOM, read by MatMat
    run_path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8")
    return run_path


def read_base_year(accounts_dir):
    """base_year of a set of accounts or of a shock (system/info.json)."""
    info = json.loads((accounts_dir / "system" / "info.json").read_text(encoding="utf-8-sig"))
    return int(info["base_year"])
