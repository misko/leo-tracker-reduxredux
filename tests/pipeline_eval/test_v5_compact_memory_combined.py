import json
from contextlib import contextmanager

import pytest

from tools.pipeline_eval.variants import v5_compact_memory_combined as combined


@pytest.mark.parametrize("failed", [False, True])
def test_combined_policies_share_one_worker_and_unwind(tmp_path, monkeypatch, failed):
    active = []

    @contextmanager
    def family():
        active.append("family")
        try:
            yield
        finally:
            assert active.pop() == "family"

    @contextmanager
    def discovery():
        active.append("discovery")
        try:
            yield [{"tracks": 29}]
        finally:
            assert active.pop() == "discovery"

    def worker(request, result, library):
        assert active == ["family", "discovery"]
        assert (request, library) == ("request", "library")
        if failed:
            raise RuntimeError("stopped receiver")
        result.write_text(
            json.dumps(dict(arms={"c0": {}, "fitted_c": {}}, metrics={"existing": 1}))
        )

    monkeypatch.setattr(combined.v5_family_memory, "family_widths_context", family)
    monkeypatch.setattr(combined.v5_sparse_discovery, "discovery_diagnostics", discovery)
    monkeypatch.setattr(combined.v5_composed_memory, "worker", worker)
    result = tmp_path / "result.json"
    if failed:
        with pytest.raises(RuntimeError, match="stopped receiver"):
            combined.worker("request", result, "library")
        assert not result.exists()
    else:
        combined.worker("request", result, "library")
        assert json.loads(result.read_text()) == {
            "arms": {"c0": {}, "fitted_c": {}},
            "boundary": combined.BOUNDARY,
            "metrics": {"existing": 1, "sparse_discovery": [{"tracks": 29}]},
        }
    assert not active
