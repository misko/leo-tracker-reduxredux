import ast
import gzip
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.pipeline_eval import cavity_entry
from tools.pipeline_eval import cavity_runtime as runtime
from tools.pipeline_eval.qualification import cavity_payload as payload
from tools.pipeline_eval.qualification import cavity_payload_trial as trial


def test_selection_retains_decorators_and_imports_for_frozen_numerics():
    source = """from dataclasses import dataclass
from somewhere import unused

@dataclass(frozen=True)
class Point:
    x: int

def f():
    return Point(2)

def debug():
    return unused()
"""
    result = payload.select_definitions(source, ("Point", "f"))
    namespace = {}
    exec(result, namespace)
    assert namespace["f"]().x == 2
    assert "unused" not in result and "debug" not in result
    with pytest.raises(ValueError, match="declared entry"):
        payload.select_definitions(source, ("absent",))


def test_closure_keeps_local_optional_paths_and_package_parents():
    files = {key: b"" for key in payload.NATIVE_SOURCES}
    files.update(
        {
            "leo/__init__.py": b"",
            "leo/engine/__init__.py": b"from . import declarations\n",
            "leo/engine/declarations.py": b"",
            "leo/engine/start.py": b"def first():\n    from .extra import fit\n    return fit()\n",
            "leo/engine/extra.py": b"def fit(): return True\n",
            "leo/engine/unused.py": b"",
        }
    )
    kept = payload.source_closure(files, "leo.engine.start")
    assert set(kept) == set(files) - {"leo/engine/unused.py"}
    files["leo/operations/__init__.py"] = b"from .maintenance import remove\n"
    files["leo/engine/start.py"] = b"from leo.operations import remove\n"
    with pytest.raises(ValueError, match="omitted export"):
        payload.source_closure(files, "leo.engine.start")


def test_pack_is_stable_and_rejects_changes_or_missing_members(tmp_path):
    files = {"x/module.py": b"y = 3\n", "z.py": b""}
    archive = tmp_path / "files.tar.gz"
    archive.write_bytes(payload.packed(files))
    assert archive.read_bytes() == payload.packed(dict(reversed(files.items())))
    manifest = {k: payload.digest(v) for k, v in files.items()}
    assert payload.read_bundle(archive, manifest) == files
    with pytest.raises(ValueError, match="digest mismatch"):
        payload.read_bundle(archive, dict(manifest, **{"z.py": "bad"}))
    with pytest.raises(ValueError, match="incomplete"):
        payload.read_bundle(archive, dict(manifest, missing=payload.digest(b"")))


@pytest.mark.parametrize(
    "path,symbolic", [("../escape.py", False), ("/absolute", False), ("x", True)]
)
def test_rejects_nonlocal_or_nonsource_archive_members(tmp_path, path, symbolic):
    archive = tmp_path / "unsafe.tar.gz"
    member = tarfile.TarInfo(path)
    if symbolic:
        member.type = tarfile.SYMTYPE
        member.linkname = "../other"
    with tarfile.open(archive, "w:gz") as out:
        out.addfile(member, io.BytesIO(b""))
    with pytest.raises(ValueError, match="unexpected source"):
        payload.read_bundle(archive, {path: payload.digest(b"")})


def test_standalone_rebuild_authenticates_the_release_and_preserves_existing_directory(tmp_path):
    receiver = runtime.install(tmp_path / "receiver")
    help_text = subprocess.check_output([sys.executable, "-IB", str(receiver), "--help"], text=True)
    assert "--native-sha256" in help_text and "--screen-center" in help_text
    assert "--native-backend" not in help_text
    assert (receiver / "native/manifest.json").is_file()
    assert (receiver / "projector.so").stat().st_size
    with pytest.raises(FileExistsError):
        runtime.install(receiver)
    assert not (receiver / "tools/pipeline_eval/qualification").exists()
    other = tmp_path / "other"
    (other / "tools").mkdir(parents=True)
    (other / "tools/__init__.py").write_text("source = 'unrelated'\n")
    script = (
        "import sys,runpy;sys.path.insert(0,sys.argv[1]);"
        "preload=sys.argv[2]=='yes';root=sys.argv[3];"
        "__import__('tools') if preload else None;"
        "sys.argv=[root,'--help'];runpy.run_path(root+'/__main__.py',run_name='__main__')"
    )
    for preload in ("yes", "no"):
        result = subprocess.run(
            [sys.executable, "-IB", "-c", script, str(other), preload, str(receiver)],
            text=True,
            capture_output=True,
        )
        if preload == "no":
            assert result.returncode == 0 and "--native-sha256" in result.stdout
        else:
            assert result.returncode != 0 and "loaded outside" in result.stderr
    with pytest.raises(ValueError, match="writable local"):
        runtime.install(Path("/mnt/qnap01/receiver-build"))


def test_measured_distribution_rebuilds_and_scientific_equivalence_includes_rf_and_status():
    parent = trial.PARENT
    root = runtime.RELEASE
    ifile = "compact-cavity-source.tar.gz"
    full = payload.read_bundle(
        parent / ifile, json.loads((parent / "bundle.json").read_bytes())["files"]
    )
    small = payload.source_closure(full)
    assert payload.packed(small) == (root / "receiver-source.tar.gz").read_bytes()
    lock = json.loads((root / "source-lock.json").read_text())["code"]
    for name in ("cavity_payload.py", "cavity_payload_trial.py"):
        assert (
            payload.digest(gzip.decompress((root / ("measured-" + name + ".gz")).read_bytes()))
            == lock[name]
        )
    for text in (v for k, v in small.items() if k.endswith(".py")):
        ast.parse(text)
    result = dict(status="ok", arms={"c0": {"rf_rms_hz": 13}}, metrics={"stage_s": {"fit": 1.2}})
    assert trial.scientific_result(result) == trial.scientific_result(
        dict(result, metrics={"stage_s": {}})
    )
    assert trial.scientific_result(result) != trial.scientific_result(
        dict(result, arms={"c0": {"rf_rms_hz": 14}})
    )
    assert trial.scientific_result(result) != trial.scientific_result(
        dict(result, status="withheld")
    )


def test_profiles_ship_the_exact_measured_sources_and_keep_distinct_operating_rules():
    base, majority, wrapped, released, interior = (
        runtime.release_files(runtime.RELEASE, profile) for profile in runtime.PROFILES
    )
    target = "leo/analysis/localization_v3/feasible.py"
    assert set(released) == set(base)
    assert {name for name in base if base[name] != released[name]} == {target}
    assert payload.digest(released[target]) == (
        "86922fff38e147c38d1c4380d71715d490d642db771c11f69d943aecd97c53bd"
    )
    entry = "tools/pipeline_eval/variants/v5_direct_cavity.py"
    assert len(base) == len(majority) == 78 and len(wrapped) == 79
    assert {name for name in base if base[name] != majority[name]} == {entry}
    assert b'"initial_compatible_support_not_majority"' in majority[entry]
    assert b"validate_geometry(tile, screen_center, width_km)" in wrapped[entry]
    assert b"initial_compatible_support_not_majority" not in wrapped[entry]
    assert interior == released | {runtime.INTERIOR_RULE: runtime.interior_rule()}
    with pytest.raises(ValueError, match="unknown standalone receiver profile"):
        runtime.release_files(runtime.RELEASE, "all")


def test_interior_installs_the_qualified_rule_with_only_the_stop_import_changed():
    installed = runtime.interior_rule()
    original = Path(runtime.__file__).with_name("variants") / "compact_tile_interior.py"
    qualified = original.read_bytes()
    assert payload.digest(qualified) == runtime.INTERIOR_RULE_SHA256
    assert installed.replace(b".compact_cavity_optimizer", b".v5_secant_fit") == qualified
    tree = ast.parse(installed)
    old = ast.parse(qualified)
    assert [ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)] == [
        ast.dump(n) for n in old.body if isinstance(n, ast.FunctionDef)
    ]
    names = [n.module for n in tree.body if isinstance(n, ast.ImportFrom)]
    assert names == ["math", "compact_cavity_optimizer"]
    optimizer = runtime.release_files(runtime.RELEASE, "interior")[
        "tools/pipeline_eval/variants/compact_cavity_optimizer.py"
    ]
    assert [
        ast.literal_eval(n.value)
        for n in ast.parse(optimizer).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "STOP_KM" for t in n.targets)
    ] == [0.020]


@pytest.mark.parametrize("near_face", [False, True])
def test_interior_launcher_runs_one_position_call_and_publishes_the_qualified_policy(
    tmp_path, near_face
):
    path = tmp_path / "receiver"
    variants = path / "tools/pipeline_eval/variants"
    variants.mkdir(parents=True)
    for directory in (path / "tools", variants.parent, variants):
        (directory / "__init__.py").write_text("PROFILE = 'interior'\n")
    original = Path(cavity_entry.__file__).read_bytes()
    (path / "__main__.py").write_bytes(runtime.interior_launcher(original))
    for filename, source in (
        ("compact_tile_interior.py", runtime.interior_rule()),
        ("compact_cavity_optimizer.py", b"STOP_KM = 0.020\n"),
    ):
        (variants / filename).write_bytes(source)
    coordinates = [37 + (12.5 / 2 / 111 if near_face else 0), -122]
    prediction = dict(
        status="ok",
        metrics={"c0_frequency_score": 130.0},
        arms={
            "c0": {"latlon": coordinates, "rf_rms_hz": 48.0},
            "fitted_c": {"latlon": [37.0, -122.0], "rf_rms_hz": 47.0},
        },
    )
    (variants / "v5_direct_cavity.py").write_text(
        "from pathlib import Path\n"
        "def run(**kwargs):\n"
        "    with Path('fit-count').open('x') as stream:\n"
        "        stream.write('1')\n"
        f"    return {prediction!r}\n"
    )
    cwd = tmp_path / "out-of-tree"
    cwd.mkdir()
    command = [sys.executable, "-IB", str(path)]
    for flag, values in (
        ("native", ("placeholder",)),
        ("native-sha256", ("placeholder",)),
        ("session", ("placeholder",)),
        ("track-config", ("placeholder",)),
        ("config-sha256", ("placeholder",)),
        ("archive", ("placeholder",)),
        ("tile", ("37", "-122")),
        ("screen-center", ("37", "-122")),
        ("width-km", ("12.5",)),
    ):
        command.extend(("--" + flag, *values))
    result = json.loads(subprocess.check_output(command, cwd=cwd))
    from tools.pipeline_eval.variants.compact_tile_interior import guard

    assert result == guard(prediction, {"center": [37.0, -122.0], "width_km": 12.5})
    assert result["status"] == ("withheld" if near_face else "ok")
    assert (cwd / "fit-count").read_text() == "1"
    with pytest.raises(ValueError, match="unexpected standalone result publication path"):
        runtime.interior_launcher(original + original)


@pytest.mark.parametrize(
    "tile,screen,width",
    [
        ((89.98, 0), (89.98, 0), 25),
        ((37, 179.99), (37, 179.99), 25),
        ((37, 179), (37, -179), 25),
        ((0, 0), (0, float("nan")), 25),
        ((0, 0), (0, 0), -1),
    ],
)
def test_public_local_chart_rejects_unsupported_geometries(tile, screen, width):
    with pytest.raises(ValueError):
        cavity_entry.validate_region(tile, screen, width)
    cavity_entry.validate_region((75.5, 142.1), (76, 142.4), 25)


def test_supervisor_deadline_and_early_worker_failure_are_preserved(tmp_path, monkeypatch):
    commands = []

    def timeout_then_stop(command, **kwargs):
        commands.append(command)
        if len(commands) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(trial.subprocess, "run", timeout_then_stop)
    code, reason = trial.supervise(["work"], "unit", tmp_path)
    assert commands[-1] == ["systemctl", "--user", "stop", "unit"]
    result, samples, rc = trial.service_result(tmp_path, code, reason)
    assert result["status"] == "timed_out" and samples == {} and rc == 124
    (tmp_path / "stderr").write_text("proof {")
    result, _, rc = trial.service_result(tmp_path, 0, None)
    assert rc and result["status"] == "failed"
    assert all(arm["latlon"] is None for arm in result["arms"].values())
