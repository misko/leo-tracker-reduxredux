import json
import sys
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import named_final_0374 as trial


def test_named_final_uses_current_active_flags_and_leaves_stock_unpatched(tmp_path, monkeypatch):
    def publish(args, *_values, **_options):
        assert args.named_survivor_finish and args.direct_residual_figures and args.direct_orbit_figures
        return {"decision": "complete"}, {"named_survivor_finish": {"requested": True, "paid_final_fit": False}}

    entry = SimpleNamespace(publish_active=publish)
    monkeypatch.setitem(sys.modules, "unified_short_bootstrap", entry)
    job = tmp_path / "request.json"
    job.write_text('{"source_pins": {}}')
    def worker(request, mode, output, *, inventory_file, **kwargs):
        assert request == job and inventory_file == job.parent / "inventory.json"
        assert kwargs["windows"] == 6770 and kwargs["admitted"] == 4644
        output.mkdir()
        if mode == "stock":
            assert entry.publish_active is publish
        else:
            assert mode == "cumulative" and entry.publish_active is not publish
            entry.publish_active(SimpleNamespace())

    monkeypatch.setattr(trial, "worker", worker)
    trial.invoke(job, "combined", tmp_path / "combined")
    assert json.loads((tmp_path / "combined/named-finish-bound.json").read_text()) == {
        "requested": True, "paid_final_fit": False,
    }
    trial.invoke(job, "stock", tmp_path / "stock")
    assert not (tmp_path / "stock/named-finish-bound.json").exists()


def test_saved_pin_rejects_altered_metadata(tmp_path):
    saved = tmp_path / "altered.json"
    saved.write_text("{}")
    with pytest.raises(ValueError, match="Saved artifact mismatch"):
        trial.verified(saved, trial.NATIVE_SHA)
