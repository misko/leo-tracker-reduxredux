import json
from pathlib import Path
import subprocess
import sys

import pytest

from reports.ALGO08.v3 import ds30_0163_blind as blind
from reports.ALGO08.v3 import ds30_0163_combined as combined
from reports.ALGO08.v3 import nomination_handoff_0419_local as prepared


def test_rank_four_preparation_cannot_execute_a_worker(tmp_path, monkeypatch):
    assignment = blind.assigned()
    assert (assignment["case"], assignment["rank"], assignment["roster_size"]) == ("DS30-0163", 4, 87)
    assert assignment["order"] == ["routed", "installed"]
    received = {}

    def capture(root, **kwargs):
        received.update(root=root, **kwargs)

    monkeypatch.setattr(prepared, "launch", capture)
    blind.prepare(tmp_path)
    assert received["root"] == tmp_path
    assert received["execute"] is False
    assert received["expected_inputs"] == blind.INPUTS
    assert received["assign"]() == assignment


def test_only_the_pinned_telemetry_writer_may_differ_from_development():
    previous = {"numerics.py": "same exact source", combined.LOGGER_SOURCE: "old logger"}
    candidate = previous | {combined.LOGGER_SOURCE: combined.LOGGER_SHA}
    assert combined.source_binding(candidate, previous) == candidate
    with pytest.raises(ValueError, match="differs"):
        combined.source_binding(candidate | {"numerics.py": "new science"}, previous)
    with pytest.raises(ValueError, match="differs"):
        combined.source_binding(previous, previous)


def test_isolated_worker_adapter_preserves_installed_bootstrap(tmp_path):
    script = Path(combined.__file__).resolve()
    snippet = (
        "import json, runpy; "
        f"scope=runpy.run_path({str(script)!r}); "
        "scope['probe'].__globals__['ready']=lambda **_: {}; "
        "print(json.dumps(scope['probe']()))"
    )
    result = subprocess.run([sys.executable, "-IB", "-c", snippet], cwd=tmp_path,
                            check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == {
        "early_leo_import": False, "guarded_worker_available": True, "worker_available": True}
