"""Prevent known-site fields and evaluation responses entering fresh wide searches."""

import importlib.util
import json
from pathlib import Path

import numpy as np


def tool(name, monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_whitelists_rf_and_forces_randomized_partition(tmp_path, monkeypatch):
    module = tool("prepare_randomized_positioning", monkeypatch)
    source = tmp_path / "source"
    (source / "evidence").mkdir(parents=True)
    tle = source / "evidence" / "a.tle"
    tle.write_text("opaque payload copied by adapter; propagation validates it later")
    meta = dict(
        session_id="scan",
        reference_utc_ns=100,
        tle_file="a.tle",
        tle_digest=module.digest(tle),
        tle_collected_ns=50,
    )
    document = dict(
        inventory=dict(**meta, observer=[37, -122], candidate_norad=123),
        series=[
            dict(
                tracklet_id="track",
                channel=1,
                edge="lower",
                actual_rf_hz=11.2e9,
                t_s=list(range(10)),
                y_hz=list(range(10)),
                candidate_ids=list(range(10)),
                matched_norad=123,
                site_latitude=37,
            )
        ],
        episodes=[
            dict(episode_id="episode", members=["track"], channel=1, known_site="do-not-export")
        ],
    )
    (source / "evidence" / "scan.json").write_text(json.dumps(document))
    (source / "inventory.json").write_text(
        json.dumps(dict(scans=[dict(session_id="scan", included=True)]))
    )
    output = tmp_path / "export"
    module.prepare(source, output)
    exported = json.loads((output / "evidence" / "scan.json").read_text())
    text = json.dumps(exported)
    for forbidden in [
        "matched_norad",
        "site_latitude",
        "observer",
        "candidate_norad",
        "do-not-export",
    ]:
        assert forbidden not in text
    assert exported["inventory"]["partition"] == "randomized"


def test_longest_selection_uses_training_scores_and_geometry_only(monkeypatch):
    module = tool("replay_position_selection", monkeypatch)
    data = dict(
        episode=np.repeat([0, 1, 2], 6),
        segment=np.repeat([0, 1, 2], 6),
        session=np.zeros(18, int),
        norad=np.repeat([100, 100, 200], 6),
        time=np.r_[np.arange(6) * 4, np.arange(6) * 6, np.arange(6) * 4],
        training=np.tile([True, False, True, False, True, False], 3),
        y=np.arange(18.0),
    )
    scores = {"0": 20.0, "1": 50.0, "2": 150.0}
    first = module.selections(data, scores)
    data["y"][~data["training"]] = 1e12
    assert module.selections(data, scores) == first
    assert first["rms100-longest-per-satellite"] == [1]
    assert first["rms200-longest-per-satellite"] == [1, 2]
