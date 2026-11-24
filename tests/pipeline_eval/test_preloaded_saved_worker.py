import importlib
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def loaded(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return importlib.import_module("preloaded_saved_worker"), importlib.import_module("preloaded_saved_score")


def test_thread_guard_rejects_an_active_import_parent(loaded, tmp_path):
    worker, _ = loaded
    (tmp_path / "1").mkdir()
    worker.require_single_thread(tmp_path)
    (tmp_path / "2").mkdir()
    with pytest.raises(ValueError, match="single-threaded"):
        worker.require_single_thread(tmp_path)


def test_child_orbit_and_position_mutation_is_absent_in_next_request(loaded, tmp_path):
    worker, _ = loaded
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import preloaded_saved_worker as run
run.preload_runtime = lambda: {'imports': 'initialized'}
def fake_publish(key, root, runtime):
    if runtime != {'imports': 'initialized'}:
        raise ValueError('Previous request crossed the isolated boundary')
    runtime.update(orbit=key, coordinates=[1, 2], native_path=str(root))
    root.write_text(key)
run.publish = fake_publish
run.sequences('preloaded', ('north', 'weak'), Path(sys.argv[2]))
"""
    subprocess.run([sys.executable, "-Bc", code, str(worker.HERE), str(tmp_path)], check=True)
    assert (tmp_path / "north").read_text() == "north"
    assert (tmp_path / "weak").read_text() == "weak"
    receipt = worker.read(tmp_path / "sequence.json")
    assert len({job["pid"] for job in receipt["jobs"]} | {receipt["initialized"]["pid"]}) == 3


def test_png_or_owner_change_invalidates_publication_parity(loaded):
    _, score = loaded
    expected = dict(images={"position": "digest"}, roles=[["observation", 22, "conditional"]])
    score.require_parity(dict(expected), expected)
    for changed in (dict(expected, images={"position": "other"}), dict(expected, roles=[])):
        with pytest.raises(ValueError, match="Isolated saved publication differs"):
            score.require_parity(changed, expected)
