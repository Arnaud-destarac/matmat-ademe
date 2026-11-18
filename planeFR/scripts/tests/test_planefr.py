"""
Tests of the PlaneFR pipeline command (planefr.py) and of the
settings helpers (_common/planefr_settings.py).

No MatMat run: the commands go to a runner that records them (and the
settings files they receive), on a copy of the templates of planeFR/parameters
in a temporary folder. Run from the root of matmat-ademe:

    uv run pytest planeFR/scripts/tests
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR / "_common"))
sys.path.insert(0, str(SCRIPTS_DIR))

import planefr  # noqa: E402
from planefr_settings import (  # noqa: E402
    Layout,
    add_suffix,
    read_template,
    set_last_year_in_path,
    set_version_in_path,
    set_year_in_path,
    write_run_settings,
)

REAL_PARAMETERS_DIR = SCRIPTS_DIR.parent / "parameters"


# === Fixtures ===

class RecordingRunner:
    """Records each command, its folder and the settings file it receives;
    on_run(call) can create the outputs a step expects, and fail_when(call)
    makes a command fail."""

    def __init__(self, on_run=None, fail_when=None):
        self.calls = []
        self.on_run = on_run
        self.fail_when = fail_when

    def __call__(self, cmd, cwd, env):
        settings = None
        if "-st" in cmd:
            settings = json.loads(Path(cmd[cmd.index("-st") + 1]).read_text(encoding="utf-8"))
        call = {"cmd": cmd, "cwd": cwd, "env": env, "settings": settings}
        self.calls.append(call)
        if self.on_run:
            self.on_run(call)
        if self.fail_when and self.fail_when(call):
            return 1
        return 0

    def matmat(self, name):
        return [c for c in self.calls if "matmat.cli" in c["cmd"] and name in c["cmd"]]

    def scripts(self):
        return [Path(c["cmd"][3]).name for c in self.calls if c["cmd"][3].endswith(".py")]


@pytest.fixture
def layout(tmp_path):
    matmat_dir = tmp_path / "MatMat" / "matmat-ademe"
    shutil.copytree(REAL_PARAMETERS_DIR, matmat_dir / "planeFR" / "parameters",
                    ignore=shutil.ignore_patterns("*.xlsx", "*.txt"))
    (matmat_dir / "data" / "4-PlaneFR").mkdir(parents=True)
    (tmp_path / "MatMat" / "datapack").mkdir()
    module_dir = tmp_path / "Module_PlaneFR"
    module_dir.mkdir()
    return Layout(matmat_dir=matmat_dir, module_dir=module_dir)


def make_dirs(layout, relative, names, base_year=None):
    """Creates sub-folders of data/<relative>, with a system/info.json if
    base_year is given."""
    for name in names:
        path = layout.data_path(relative) / name
        path.mkdir(parents=True, exist_ok=True)
        if base_year is not None:
            (path / "system").mkdir(exist_ok=True)
            (path / "system" / "info.json").write_text(json.dumps({"base_year": base_year}))


# === planefr_settings ===

def test_year_and_version_in_path():
    path = "./4-PlaneFR/1-accounts/Exiobase/3.11.2_2019/3.11.2_pxp_2019"
    assert set_year_in_path(path, 2015) == "./4-PlaneFR/1-accounts/Exiobase/3.11.2_2015/3.11.2_pxp_2015"
    assert set_last_year_in_path(path, 2015) == "./4-PlaneFR/1-accounts/Exiobase/3.11.2_2019/3.11.2_pxp_2015"
    assert set_version_in_path(path, "3.10.2") == "./4-PlaneFR/1-accounts/Exiobase/3.10.2_2019/3.10.2_pxp_2019"


def test_add_suffix():
    assert add_suffix("SSP2_2050", "_agri") == "SSP2_2050_agri"
    assert add_suffix("Base_year_agri", "_agri") == "Base_year_agri"
    assert add_suffix("SSP2_2050", "") == "SSP2_2050"


def test_templates_read_with_posix_separators(layout):
    settings = read_template(layout, "2-gmrio_to_snac_s/gmrio_to_snac_S_FR.json")
    assert "\\" not in json.dumps(settings["path_in"]) + settings["path_out"]
    assert settings["path_in"]["accounts"].startswith("./4-PlaneFR/")


def test_write_run_settings_expands_token_and_keeps_template(layout):
    template = "2-gmrio_to_snac_s/gmrio_to_snac_S_FR.json"
    original = (layout.parameters_dir / template).read_text(encoding="utf-8")
    path = write_run_settings(layout, template, read_template(layout, template))

    assert path == layout.run_settings_dir / template
    written = json.loads(path.read_text(encoding="utf-8"))
    bridges = written["path_in"]["bridges"]
    assert bridges == f"{layout.parameters_dir.resolve().as_posix()}/2-gmrio_to_snac_s/bridge_matrices.xlsx"
    assert written["m_row_mode"] == "foreign_global_feedback"
    assert (layout.parameters_dir / template).read_text(encoding="utf-8") == original


# === Batch steps ===

def test_exiobase3_eeio(layout):
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).exiobase3_eeio() == 0

    adapter = runner.matmat("exiobase3_eeio")
    assert [c["settings"]["base_year"] for c in adapter] == [2015, 2019]
    assert adapter[0]["settings"]["path_out"] == "./4-PlaneFR/1-accounts/Exiobase/3.11.2_2015"
    engine = runner.matmat("eeio")
    assert [c["settings"]["path_out"] for c in engine] == [
        "./4-PlaneFR/Outputs/World/Base_year_2015", "./4-PlaneFR/Outputs/World/Base_year_2019"]
    assert engine[1]["settings"]["path_in"]["accounts"] == \
        "./4-PlaneFR/1-accounts/Exiobase/3.11.2_2019/3.11.2_pxp_2019"
    assert all(c["env"]["PLANEFR_EXIOBASE_VERSION"] == "3.11.2" for c in runner.calls)
    assert all(c["cwd"] == layout.matmat_dir for c in runner.calls)


def test_gmrio_to_snac_s(layout):
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).gmrio_to_snac_s() == 0

    assert [c["settings"]["path_out"] for c in runner.matmat("gmrio_to_snac_s")] == [
        "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/3.11.2_pxp_2015",
        "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/3.11.2_pxp_2019"]
    assert not runner.scripts()


def test_gmrio_to_snac_s_ssps_reference_first_and_f_x_dom_copied(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050_agri", ["SSP2_2050", "Base_year_agri", "SSP1_2050"])
    extensions = read_template(layout, "2-gmrio_to_snac_s/gmrio_to_snac_S_SSPs.json")["extension_names"]

    def create_outputs(call):
        out = layout.data_path(call["settings"]["path_out"])
        for ext in extensions:
            (out / "extensions" / f"dom_{ext}").mkdir(parents=True, exist_ok=True)
            (out / "extensions" / f"dom_{ext}" / "F_x_dom.pkl").write_text(out.name)

    runner = RecordingRunner(on_run=create_outputs)
    assert planefr.Pipeline(layout, "3.11.2", runner).gmrio_to_snac_s_ssps("_agri") == 0

    runs = runner.matmat("gmrio_to_snac_s")
    assert [c["settings"]["path_out"] for c in runs] == [
        "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/SSPs_agri/Base_year_agri",
        "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/SSPs_agri/SSP1_2050_agri",
        "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/SSPs_agri/SSP2_2050_agri"]
    assert runs[1]["settings"]["path_in"]["accounts"] == "./4-PlaneFR/Outputs/World/SSP1_2050_agri"
    copied = layout.data_path("4-PlaneFR/Outputs_inter/gmrio_to_snac_s/SSPs_agri/SSP2_2050_agri"
                              f"/extensions/dom_{extensions[0]}/F_x_dom.pkl")
    assert copied.read_text() == "Base_year_agri"


def test_update_calib_fr_runs_from_datapack(layout):
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).update_calib_fr() == 0

    runs = runner.matmat("update_calib_fr")
    assert all(c["cwd"] == layout.datapack_dir for c in runs)
    path_in = runs[0]["settings"]["path_in"]
    assert path_in["newer_accounts"] == "./4-PlaneFR/Outputs_inter/gmrio_to_snac_s/3.11.2_pxp_2015"
    assert path_in["older_accounts"] == "./3-workshops/1-accounts/MatMat/3.10.2_France_2015"
    assert runs[1]["settings"]["path_out"] == "./4-PlaneFR/Outputs/France/Base_year_2019"


def test_update_calib_fr_ssps_finds_accounts_sub_folder(layout):
    base = "4-PlaneFR/Outputs_inter/gmrio_to_snac_s/SSPs"
    make_dirs(layout, base, ["Base_year_2015"], base_year=2015)
    make_dirs(layout, f"{base}/SSP1_2050", ["3.11.2_pxp_2019"], base_year=2019)
    make_dirs(layout, base, ["empty"])

    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).update_calib_fr_ssps() == 0

    runs = runner.matmat("update_calib_fr")
    assert [c["settings"]["path_in"]["newer_accounts"] for c in runs] == [
        f"./{base}/Base_year_2015", f"./{base}/SSP1_2050/3.11.2_pxp_2019"]
    assert runs[1]["settings"]["path_in"]["older_accounts"].endswith("3.10.2_France_2019")
    assert runs[1]["settings"]["path_out"] == "./4-PlaneFR/Outputs/France/SSP1_2050"


def test_engine_ssps(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050", ["SSP2_2050"])
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine_ssps() == 0

    (run,) = runner.matmat("eeio")
    assert run["settings"]["path_in"]["shock"] == "./4-PlaneFR/2-shocks/3-SSPs_2050/SSP2_2050"
    assert run["settings"]["path_in"]["accounts"] == "./4-PlaneFR/Outputs/World/Base_year_2015"
    assert run["settings"]["path_out"] == "./4-PlaneFR/Outputs/World/SSP2_2050"


def test_france_engine_groups_and_reference_copy(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["SSP2_2050", "Base_year_2015", "Base_year_2019"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050", "TEND_2050"])

    def create_outputs(call):
        (Path(call["settings"]["path_out"]) / "extensions").mkdir(parents=True, exist_ok=True)

    runner = RecordingRunner(on_run=create_outputs)
    assert planefr.Pipeline(layout, "3.11.2", runner).engine() == 0

    out = (layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw").as_posix()
    runs = [(c["settings"]["path_in"]["accounts"].rsplit("/", 1)[1],
             c["settings"]["path_in"]["shock"] and c["settings"]["path_in"]["shock"].rsplit("/", 1)[1],
             c["settings"]["path_out"]) for c in runner.matmat("eeio")]
    assert runs == [
        ("Base_year_2015", None, f"{out}/no_SSP/Base_year_2015"),
        ("Base_year_2019", None, f"{out.rsplit('/', 1)[0]}/2019_raw/2019_FR"),
        ("Base_year_2015", "S1_2050", f"{out}/no_SSP/S1_2050"),
        ("Base_year_2015", "TEND_2050", f"{out}/no_SSP/TEND_2050"),
        ("SSP2_2050", "S1_2050", f"{out}/SSP2_2050/S1_2050"),
        ("SSP2_2050", "TEND_2050", f"{out}/SSP2_2050/TEND_2050"),
    ]
    assert (layout.module_dir / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw" / "SSP2_2050" / "Base_year_2015" / "extensions").is_dir()


def test_france_engine_no_ssp_only(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["SSP2_2050", "Base_year_2015", "Base_year_2019"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050", "TEND_2050"])

    def create_outputs(call):
        (Path(call["settings"]["path_out"]) / "extensions").mkdir(parents=True, exist_ok=True)

    runner = RecordingRunner(on_run=create_outputs)
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(no_ssp_only=True) == 0

    out = (layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw").as_posix()
    assert [c["settings"]["path_out"] for c in runner.matmat("eeio")] == [
        f"{out}/no_SSP/Base_year_2015",
        f"{out}/no_SSP/S1_2050",
        f"{out}/no_SSP/TEND_2050",
    ]
    assert not (layout.module_dir / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw" / "SSP2_2050").exists()


def test_france_engine_no_ssp_only_fails_without_reference_accounts(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["SSP2_2050"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050"])
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(no_ssp_only=True) == 1
    assert not [c for c in runner.matmat("eeio") if c["settings"]["path_in"]["shock"]]


def test_france_engine_agri_suffix(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France_agri", ["SSP2_2050", "Base_year_agri"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050_agri", ["Base_year_agri", "S1_2050"])

    def create_outputs(call):
        (Path(call["settings"]["path_out"]) / "extensions").mkdir(parents=True, exist_ok=True)

    runner = RecordingRunner(on_run=create_outputs)
    assert planefr.Pipeline(layout, "3.11.2", runner).engine("_agri") == 0

    out = (layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw").as_posix()
    assert [c["settings"]["path_out"] for c in runner.matmat("eeio")] == [
        f"{out}/no_SSP_agri/Base_year_agri",
        f"{out}/no_SSP_agri/S1_2050_agri",
        f"{out}/SSP2_2050_agri/S1_2050_agri",  # Base_year_agri copied, not computed
    ]
    assert (layout.module_dir / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw" / "SSP2_2050_agri" / "Base_year_agri").is_dir()


def test_batch_continues_after_a_failure(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050", ["SSP1_2050", "SSP2_2050"])
    runner = RecordingRunner(fail_when=lambda call: "SSP1_2050" in call["settings"]["path_out"])
    assert planefr.Pipeline(layout, "3.11.2", runner).engine_ssps() == 1
    assert len(runner.matmat("eeio")) == 2


def test_missing_input_folder_fails(layout):
    assert planefr.Pipeline(layout, "3.11.2", RecordingRunner()).engine_ssps() == 1


# === Chains and command line ===

def scripts_of(stages, monkeypatch, pipeline):
    """Python scripts and batch steps run by a chain, batch steps stubbed; a
    batch step called with keyword arguments is shown as "<step> key=value"."""
    for step in ("exiobase3_eeio", "gmrio_to_snac_s", "gmrio_to_snac_s_ssps",
                 "update_calib_fr", "update_calib_fr_ssps", "engine", "engine_ssps", "regions_agri"):
        monkeypatch.setattr(pipeline, step, lambda *args, _step=step, **kwargs: pipeline.runner.calls.append(
            {"cmd": ["step", _step, *args], "kwargs": kwargs}) or 0)
    assert planefr.run_chain("test", stages()) == 0
    return [" ".join([c["cmd"][1], *(f"{k}={v}" for k, v in c["kwargs"].items() if v)]) if c["cmd"][0] == "step"
            else " ".join([Path(c["cmd"][3]).name, *c["cmd"][4:]])
            for c in pipeline.runner.calls]


FRANCE_SHOCKS = ["engine no_ssp_only=True", "reformat_d_cba_monde_europe.py",
                 "reformat_d_cba_k.py", "export_dS.py", "compute_ds_x_dom.py"]
SSP_SHOCKS = ["extract_S_SSPs.py", "generate_shock_dS.py", "engine_ssps", "gmrio_to_snac_s_ssps",
              "update_calib_fr_ssps"]
OUTPUTS = ["engine", "reformat_d_cba_monde_europe.py", "reformat_d_cba_k.py",
           "compute_ds_x_dom.py --only-f-y-tot", "build_scenario_groups.py"]


def test_france_shocks_chain(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert scripts_of(pipeline.chain_france_shocks, monkeypatch, pipeline) == FRANCE_SHOCKS


def test_france_shocks_chain_manual_only(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert scripts_of(lambda: pipeline.chain_france_shocks(manual_only=True), monkeypatch, pipeline) == \
        ["compute_ds_x_dom.py"]


def test_main_france_shocks_manual_only(layout):
    runner = RecordingRunner()
    assert planefr.main(["france-shocks", "--manual-only"], layout=layout, runner=runner) == 0
    assert runner.scripts() == ["compute_ds_x_dom.py"]


def test_ssp_shocks_chain(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert scripts_of(pipeline.chain_ssp_shocks, monkeypatch, pipeline) == SSP_SHOCKS
    assert all(c["cmd"][2:] == [""] for c in pipeline.runner.calls if c["cmd"][0] == "step")


def test_outputs_chain(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert scripts_of(pipeline.chain_outputs, monkeypatch, pipeline) == OUTPUTS


def test_outputs_chain_ssps(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    ran = scripts_of(lambda: pipeline.chain_outputs(ssps_only=True), monkeypatch, pipeline)
    assert ran == ["engine ssps_only=True", *OUTPUTS[1:]]


def test_france_engine_ssps_only(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["SSP1_2050", "SSP2_2050", "Base_year_2015", "Base_year_2019"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050"])
    out = layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw"
    (out / "no_SSP" / "Base_year_2015" / "extensions").mkdir(parents=True)  # previous run

    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(ssps_only=True) == 0
    assert [c["settings"]["path_out"] for c in runner.matmat("eeio")] == [
        f"{out.as_posix()}/SSP1_2050/S1_2050", f"{out.as_posix()}/SSP2_2050/S1_2050"]
    assert (out / "SSP2_2050" / "Base_year_2015" / "extensions").is_dir()


def test_france_engine_ssps_only_fails_without_ssp_accounts(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["Base_year_2015"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050"])
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(ssps_only=True) == 1
    assert not runner.calls


@pytest.mark.parametrize("change, expected", [
    ("All", ["base accounts", "france-shocks", "ssp-shocks", "outputs"]),
    ("RoW_shocks_change", ["ssp-shocks", "outputs --ssps"]),
    ("France_shocks_change", ["france-shocks", "outputs"]),
    ("France_shocks_dS_change", ["france-shocks --manual-only", "outputs"]),
    ("Agri", ["agri"]),
])
def test_change_options(layout, monkeypatch, change, expected):
    ran = []
    monkeypatch.setattr(planefr, "run_chain", lambda title, stages: ran.append((title, stages)) or 0)
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert planefr.main([f"--{change}", "--version", "3.10.2"], layout=layout) == 0
    (title, stages), = ran
    assert title == f"--{change} (version 3.10.2)"
    chains = {"base accounts": pipeline._base_accounts_stages, "ssp-shocks": pipeline.chain_ssp_shocks,
              "outputs": pipeline.chain_outputs, "outputs --ssps": lambda: pipeline.chain_outputs(ssps_only=True),
              "france-shocks": pipeline.chain_france_shocks,
              "france-shocks --manual-only": lambda: pipeline.chain_france_shocks(manual_only=True),
              "agri": pipeline.chain_agri}
    assert [s.name for s in stages] == [s.name for name in expected for s in chains[name]()]


POST = OUTPUTS[1:]


@pytest.mark.parametrize("change, expected", [
    ("France_shocks_change",
     FRANCE_SHOCKS + ["generate_shock_agri.py --only transitions", "regions_agri", "engine", "engine _agri"]
     + POST),
    ("France_shocks_dS_change",
     ["compute_ds_x_dom.py", "generate_shock_agri.py --only transitions", "regions_agri", "engine",
      "engine _agri"] + POST),
    ("RoW_shocks_change",
     SSP_SHOCKS + ["generate_shock_agri.py --only ssps", "engine_ssps _agri", "gmrio_to_snac_s_ssps _agri",
                   "update_calib_fr_ssps _agri", "regions_agri", "engine ssps_only=True",
                   "engine _agri ssps_only=True"] + POST),
])
def test_change_with_agri(layout, monkeypatch, change, expected):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    show_args = lambda c: c["cmd"][0] == "step" and c["cmd"][2:] == ["_agri"]  # noqa: E731
    ran = scripts_of(lambda: pipeline.chain_change(change, agri=True), monkeypatch, pipeline)
    # suffix shown for the _agri batch steps
    ran = [name.replace(" ", " _agri ", 1) if show_args(c) and " " in name else name + " _agri" if show_args(c)
           else name for name, c in zip(ran, pipeline.runner.calls)]
    assert ran == expected


def test_all_with_agri_post_processing_once(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    ran = scripts_of(lambda: pipeline.chain_change("All", agri=True), monkeypatch, pipeline)
    assert ran.count("build_scenario_groups.py") == 1
    assert ran.count("engine_ssps") == 2  # SSP and SSP_agri projections
    assert "generate_shock_agri.py" in ran


def test_main_change_with_agri(layout, monkeypatch):
    ran = []
    monkeypatch.setattr(planefr, "run_chain", lambda title, stages: ran.append(title) or 0)
    assert planefr.main(["--France_shocks_change", "--Agri"], layout=layout) == 0
    assert ran == ["--France_shocks_change --Agri (version 3.11.2)"]


@pytest.mark.parametrize("agri", [False, True])
def test_france_and_ssp_changes_combined(layout, monkeypatch, agri):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    ran = scripts_of(lambda: pipeline.chain_change(["France_shocks_change", "RoW_shocks_change"], agri),
                     monkeypatch, pipeline)
    agri_part = ["generate_shock_agri.py", "engine_ssps", "gmrio_to_snac_s_ssps", "update_calib_fr_ssps",
                 "regions_agri"]
    engines = ["engine", "engine"] if agri else ["engine"]
    assert ran == FRANCE_SHOCKS + SSP_SHOCKS + (agri_part if agri else []) + engines + POST
    # Same as All, without the base accounts
    all_ran = scripts_of(lambda: pipeline.chain_change("All", agri), monkeypatch, pipeline)[len(ran):]
    assert all_ran[4:] == ran


def test_france_dS_and_ssp_changes_combined(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    ran = scripts_of(lambda: pipeline.chain_change(["France_shocks_dS_change", "RoW_shocks_change"]),
                     monkeypatch, pipeline)
    assert ran == ["compute_ds_x_dom.py"] + SSP_SHOCKS + ["engine"] + POST


def test_main_combined_changes(layout, monkeypatch):
    ran = []
    monkeypatch.setattr(planefr, "run_chain", lambda title, stages: ran.append(title) or 0)
    assert planefr.main(["--France_shocks_change", "--RoW_shocks_change", "--Agri"], layout=layout) == 0
    assert ran == ["--France_shocks_change --RoW_shocks_change --Agri (version 3.11.2)"]


def prepare_selection(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France", ["SSP1_2050", "SSP2_2050", "Base_year_2015", "Base_year_2019"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050", "S2_2050", "TEND_2050"])
    out = layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw"
    (out / "no_SSP" / "Base_year_2015" / "extensions").mkdir(parents=True)  # previous run
    return out.as_posix()


def test_france_engine_selection(layout):
    out = prepare_selection(layout)
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(
        france=("S1_2050",), row=("no_SSP", "SSP2_2050")) == 0
    # No baseline run, only the combinations of both lists
    assert [c["settings"]["path_out"] for c in runner.matmat("eeio")] == [
        f"{out}/no_SSP/S1_2050", f"{out}/SSP2_2050/S1_2050"]


def test_france_engine_selection_france_only(layout):
    out = prepare_selection(layout)
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(france=("S2_2050", "TEND_2050")) == 0
    assert sorted(c["settings"]["path_out"].replace(out, "") for c in runner.matmat("eeio")) == sorted(
        f"/{group}/{scenario}" for group in ("no_SSP", "SSP1_2050", "SSP2_2050")
        for scenario in ("S2_2050", "TEND_2050"))


def test_france_engine_selection_agri_suffix(layout):
    make_dirs(layout, "4-PlaneFR/Outputs/France_agri", ["SSP2_2050", "Base_year_agri"])
    # Shock folders carry the suffix, as written by generate_shock_agri.py
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050_agri",
              ["Base_year_agri", "S1_2050_agri", "S2_2050_agri"])
    out = (layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2050_raw").as_posix()
    (Path(out) / "no_SSP_agri" / "Base_year_agri" / "extensions").mkdir(parents=True)  # previous run
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).engine(
        "_agri", france=("S1_2050",), row=("SSP2_2050",)) == 0
    assert [c["settings"]["path_out"] for c in runner.matmat("eeio")] == [f"{out}/SSP2_2050_agri/S1_2050_agri"]


def test_france_engine_selection_unknown_names_fail(layout):
    prepare_selection(layout)
    assert planefr.Pipeline(layout, "3.11.2", RecordingRunner()).engine(france=("S9_2050",)) == 1
    assert planefr.Pipeline(layout, "3.11.2", RecordingRunner()).engine(row=("SSP9_2050",)) == 1


def test_selection_reaches_only_the_final_engine(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner(), france=("S1_2050",), row=("SSP2_2050",))
    ran = scripts_of(lambda: pipeline.chain_change(["France_shocks_change"]), monkeypatch, pipeline)
    # france-shocks engine (no_SSP, for export_dS) is not restricted, the final one is
    assert ran == FRANCE_SHOCKS + ["engine france=('S1_2050',) row=('SSP2_2050',)"] + POST
    assert "engine no_ssp_only=True" in ran


def test_main_selection(layout, monkeypatch):
    seen = []
    monkeypatch.setattr(planefr, "run_chain",
                        lambda title, stages: seen.append(title) or 0)
    monkeypatch.setattr(planefr.Pipeline, "chain_outputs",
                        lambda self, *a, **k: seen.append((self.france, self.row)) or [])
    assert planefr.main(["outputs", "--France", "S1_2050", "--RoW", "no_SSP", "SSP2_2050"],
                        layout=layout) == 0
    assert seen[0] == (("S1_2050",), ("no_SSP", "SSP2_2050"))
    seen.clear()
    assert planefr.main(["--France_shocks_change", "--France", "S1_2050"], layout=layout) == 0
    assert planefr.main(["step", "engine"], layout=layout) == 0
    with pytest.raises(SystemExit):
        planefr.main(["ssp-shocks", "--France", "S1_2050"], layout=layout)


def test_selection_with_all_restricts_only_the_final_engine(layout, monkeypatch):
    argv = ["--All", "--France", "S1_2050"]
    ran = []
    monkeypatch.setattr(planefr, "run_chain", lambda title, stages: ran.extend(stages) or 0)
    seen = []
    monkeypatch.setattr(planefr.Pipeline, "engine", lambda self, *a, **k: seen.append(k) or 0)
    assert planefr.main(argv, layout=layout, runner=RecordingRunner()) == 0
    for stage in ran:
        if "France engine" in stage.name:
            stage.action()
    assert seen == [{"no_ssp_only": True},                                          # france-shocks engine
                    {"ssps_only": False, "france": ("S1_2050",), "row": ()}]       # final engine


def test_help_lists_existing_scenarios(layout, capsys):
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050", ["S1_2050", "TEND_2050"])
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050", ["SSP1_2050", "SSP2_2050"])
    assert planefr.list_scenarios(layout) == (["S1_2050", "TEND_2050"], ["no_SSP", "SSP1_2050", "SSP2_2050"])
    with pytest.raises(SystemExit):
        planefr.main(["--help"], layout=layout)
    out = capsys.readouterr().out
    assert "S1_2050, TEND_2050" in out and "no_SSP, SSP1_2050, SSP2_2050" in out


def test_main_requires_a_change_or_a_command(layout):
    with pytest.raises(SystemExit):
        planefr.main([], layout=layout, runner=RecordingRunner())
    with pytest.raises(SystemExit):
        planefr.main(["--RoW_shocks_change", "outputs"], layout=layout, runner=RecordingRunner())


def test_all_combines_the_three_chains(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    base_accounts = ["exiobase3_eeio", "extract_f_y_tot.py", "gmrio_to_snac_s", "update_calib_fr"]
    assert scripts_of(lambda: pipeline.chain_change("All"), monkeypatch, pipeline) == \
        base_accounts + FRANCE_SHOCKS + SSP_SHOCKS + OUTPUTS


def test_full_command_removed(layout):
    with pytest.raises(SystemExit):
        planefr.main(["full"], layout=layout, runner=RecordingRunner())


def test_agri_chain(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner())
    assert scripts_of(pipeline.chain_agri, monkeypatch, pipeline) == \
        ["generate_shock_agri.py", *SSP_SHOCKS[2:], "regions_agri", *OUTPUTS]
    assert all("_agri" in c["cmd"][2:] for c in pipeline.runner.calls
               if c["cmd"][0] == "step" and c["cmd"][1] != "regions_agri")


def test_agri_chain_selection_skips_regions_agri(layout, monkeypatch):
    pipeline = planefr.Pipeline(layout, "3.11.2", RecordingRunner(), france=("S1_2050",))
    assert "regions_agri" not in scripts_of(pipeline.chain_agri, monkeypatch, pipeline)


def test_regions_agri(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050_agri", ["Base_year_agri"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050_agri", ["Base_year_agri"])
    gmrio_out = "4-PlaneFR/Outputs_inter/gmrio_to_snac_s/Base_year_2019_agri"
    # gmrio_to_snac_s writes its accounts into a <version>_pxp_<year> sub-folder
    make_dirs(layout, gmrio_out, ["3.11.2_pxp_2019"], base_year=2019)

    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).regions_agri() == 0
    world, france = runner.matmat("eeio")
    assert world["settings"]["path_in"] == {**world["settings"]["path_in"],
                                            "accounts": "./4-PlaneFR/Outputs/World/Base_year_2019",
                                            "shock": "./4-PlaneFR/2-shocks/3-SSPs_2050_agri/Base_year_agri"}
    assert world["settings"]["path_out"] == "./4-PlaneFR/Outputs/World/Base_year_2019_agri"
    (gmrio,) = runner.matmat("gmrio_to_snac_s")
    assert gmrio["settings"]["path_in"]["accounts"] == "./4-PlaneFR/Outputs/World/Base_year_2019_agri"
    assert gmrio["settings"]["path_out"] == f"./{gmrio_out}"
    (calib,) = runner.matmat("update_calib_fr")
    assert calib["settings"]["path_in"]["newer_accounts"] == f"./{gmrio_out}/3.11.2_pxp_2019"
    assert calib["settings"]["path_in"]["older_accounts"].endswith("3.10.2_France_2019")
    assert calib["settings"]["path_out"] == "./4-PlaneFR/Outputs/France_agri/Base_year_2019_agri"
    assert france["settings"]["path_in"]["accounts"] == "./4-PlaneFR/Outputs/France_agri/Base_year_2019_agri"
    assert france["settings"]["path_in"]["shock"] == "./4-PlaneFR/2-shocks/1-transitions_2050_agri/Base_year_agri"
    out = layout.module_dir.resolve() / "data" / "Outputs_MatMat" / "3.11.2" / "2019_raw" / "2019_FR_agri"
    assert france["settings"]["path_out"] == out.as_posix()


def test_regions_agri_stops_at_first_failure(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050_agri", ["Base_year_agri"])
    make_dirs(layout, "4-PlaneFR/2-shocks/1-transitions_2050_agri", ["Base_year_agri"])
    runner = RecordingRunner(fail_when=lambda c: "eeio" in c["cmd"])
    assert planefr.Pipeline(layout, "3.11.2", runner).regions_agri() == 1
    assert len(runner.calls) == 1


def test_regions_agri_fails_without_shocks(layout):
    runner = RecordingRunner()
    assert planefr.Pipeline(layout, "3.11.2", runner).regions_agri() == 1
    assert not runner.calls


def test_chain_stops_at_first_failure():
    ran = []
    stages = [planefr.Stage(name, lambda name=name, code=code: ran.append(name) or code)
              for name, code in [("a", 0), ("b", 3), ("c", 0)]]
    assert planefr.run_chain("test", stages) == 3
    assert ran == ["a", "b"]


def test_main_step_with_suffix(layout):
    make_dirs(layout, "4-PlaneFR/2-shocks/3-SSPs_2050_agri", ["SSP2_2050"])
    runner = RecordingRunner()
    code = planefr.main(["step", "engine_ssps", "--suffix", "_agri", "--version", "3.10.2"],
                        layout=layout, runner=runner)
    assert code == 0
    (run,) = runner.calls
    assert run["settings"]["path_out"] == "./4-PlaneFR/Outputs/World/SSP2_2050_agri"
    assert run["env"]["PLANEFR_EXIOBASE_VERSION"] == "3.10.2"


def test_main_rejects_suffix_on_base_year_step(layout):
    with pytest.raises(SystemExit):
        planefr.main(["step", "exiobase3_eeio", "--suffix", "_agri"], layout=layout, runner=RecordingRunner())
