from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import isolated_salvage_south as replay


def test_replay_uses_the_original_combined_binding_and_saved_worker(monkeypatch):
    events = []
    paths = tuple(Path(name) for name in ("request", "inventory", "output"))

    @contextmanager
    def isolated_policy():
        events.append("enter combined")
        yield
        events.append("exit combined")

    def publish(args):
        assert vars(args) == dict(direct_orbit_figures=True, direct_residual_figures=True)
        events.append("actual publication")

    def worker(job, mode, output, *, source_pins, inventory_file, **options):
        assert (job, inventory_file, output) == paths and mode == "cumulative"
        assert source_pins == {"combined": "pin"} and options == replay.SETTINGS
        entry.publish_active(SimpleNamespace())

    entry = SimpleNamespace(publish_active=publish)
    monkeypatch.setitem(sys.modules, "unified_short_bootstrap", entry)
    monkeypatch.setitem(sys.modules, "isolated_salvage", SimpleNamespace(binding=isolated_policy))
    monkeypatch.setattr(replay, "inherited_sources", lambda: {"combined": "pin"})
    monkeypatch.setattr(replay, "worker", worker)
    replay.candidate(*paths)
    assert events == ["enter combined", "actual publication", "exit combined"]


def test_omission_fix_is_false_even_if_numerically_close():
    assert replay.decision_label("ok", -.1) == "false_fix"
    assert replay.decision_label("complete", -.1) == "false_fix"
    assert replay.decision_label("withheld", -.1) == "withheld"
    assert replay.decision_label("complete", .1) == "fix"
    assert replay.decision_label("withheld", .1) == "false_withhold"
    with pytest.raises(ValueError, match="geographic decision"):
        replay.decision_label("failed", -.1)
