from pathlib import Path

import pytest


def test_withhold_proof_removes_only_the_current_recording_identity(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    from visit_frame_raw_0107 import proof

    raw = dict(native_sha256="new-id", graph_proof=dict(proven=True,
        curvature_extent=dict(native_sha256="new-id", maximum_span=.8), cpu_s=.1))
    assert proof(raw) == dict(proven=True, curvature_extent=dict(maximum_span=.8))
    raw["graph_proof"]["curvature_extent"]["native_sha256"] = "older-id"
    with pytest.raises(ValueError, match="must bind its own"):
        proof(raw)
