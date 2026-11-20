import json
from collections import Counter
from contextlib import contextmanager

import pytest

from tools.pipeline_eval.variants import v5_secant_two_refresh as combined


def test_secant_worker_runs_inside_limited_phase_context(monkeypatch, tmp_path):
    active = []

    @contextmanager
    def limited():
        active.append("limited")
        counts = Counter()
        try:
            yield counts
        finally:
            counts["initial_rounds"] = 6
            active.pop()

    def secant(request, result, library, mode):
        assert active == ["limited"]
        assert (request, library, mode) == ("request", "compact-library", "secant")
        result.write_text(json.dumps(dict(metrics={"position_optimizer": {"evaluations": 18}})))

    monkeypatch.setattr(combined.v5_two_refresh, "early_phase_policy", limited)
    monkeypatch.setattr(combined.v5_secant_fit, "worker", secant)
    path = tmp_path / "result.json"
    combined.worker("request", path, "compact-library")
    result = json.loads(path.read_bytes())
    assert active == [] and result["boundary"] == combined.BOUNDARY
    assert result["metrics"] == {
        "combined_source_sha256": combined.DEPENDENCIES,
        "outer_phase_limit": 2,
        "phase_fit_counts": {"initial_rounds": 6},
        "position_optimizer": {"evaluations": 18},
    }


def test_source_lock_rejects_changed_parent_before_compiling_or_reading_inputs(monkeypatch):
    monkeypatch.setattr(combined, "DEPENDENCIES", {"v5_secant_fit.py": "0" * 64})
    with pytest.raises(ValueError, match="locked scientific source"):
        combined.run(None, None)
