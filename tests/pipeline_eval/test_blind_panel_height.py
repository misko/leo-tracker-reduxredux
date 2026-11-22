import hashlib
from importlib import import_module
import json
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import holdout_geography, waveform_site_model
from tools.pipeline_eval.qualification.score_paired_holdout import lock, score


panel = import_module("reports.ALGO08.regional-release.blind_panel")
SEED = "24" * 32


@pytest.fixture
def metadata_only(monkeypatch, tmp_path):
    observed = []
    snapshot = tmp_path / "source.tle"
    snapshot.write_bytes(b"sealed orbit fixture")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    monkeypatch.setattr(panel, "authentic_history", lambda: (
        12, b"nominal", [dict(sha256=digest, collected_utc_ns=12)], {digest: snapshot}))
    monkeypatch.setattr(panel, "revised", lambda *args: (b"updated", 13, None))
    monkeypatch.setattr(panel.clock_transfer_inputs, "_true_bank", lambda *args: None)
    monkeypatch.setattr(waveform_site_model.orbit, "_constellation", lambda *args: [])
    monkeypatch.setattr(waveform_site_model.orbit, "_emitters", lambda *args: [])
    monkeypatch.setattr(waveform_site_model, "pulse_bank", lambda: {"lower": None, "upper": None})
    monkeypatch.setattr(waveform_site_model, "iq", lambda *args: None)
    monkeypatch.setattr(waveform_site_model, "SWEEPS", 1)
    original_scene = waveform_site_model.make_scene

    def scene(*args, **kwargs):
        scan, info = original_scene(*args, **kwargs)
        observed.append((scan[0]["edge"], info))
        return scan, info

    monkeypatch.setattr(waveform_site_model, "make_scene", scene)

    class Writer:
        def __init__(self, root, recording, **kwargs):
            self.path = root / recording
            self.path.mkdir()
            (self.path / "manifest.json").write_text(json.dumps(kwargs))

        def append(self, *, samples, **kwargs):
            assert samples is None
            assert "height_m" not in json.dumps(kwargs)

        def finish(self, **kwargs):
            return self.path

    monkeypatch.setattr(panel, "ShortWindowWriter", Writer)
    def reader(path):
        payload = (path / "manifest.json").read_bytes()
        return SimpleNamespace(manifest_sha256=hashlib.sha256(payload).hexdigest(),
                               manifest=SimpleNamespace(**json.loads(payload)))

    monkeypatch.setattr(panel, "ShortWindowReader", reader)
    monkeypatch.setattr("tools.pipeline_eval.qualification.score_paired_holdout.ShortWindowReader", reader)
    return observed


@pytest.mark.parametrize(("fresh", "public_sha", "private_sha", "heights"), [
    (False, "c1d55f86cd0bd897e8d5b093b2e40bac263e541ef6cd0dfe5205bd7dd166e97c",
     "afe6a3bd0f274bf16e93c1b13e9544a66bf4afc9123bf366fc595ac61fa0d02a",
     (75.45681254470237, 79.27694593726173)),
    (True, "45f036391f4cb8a41cddfb6f36f633e0dd19a95e92fc0e0ea3f9b50b3b73e2dc",
     "7f520c8314ff1c2b40766b934760ec7f321c3ea372df4494fdc3aae734e3e5d1",
     (36.2045684582802, 103.82905352989229)),
])
def test_default_panels_preserve_their_seeded_public_and_private_bytes(
    metadata_only, tmp_path, fresh, public_sha, private_sha, heights,
):
    root = tmp_path / "case"
    panel.generate(root, SEED, fresh)
    actual = tuple(hashlib.sha256((root / path).read_bytes()).hexdigest()
                   for path in ("public/panel.json", "scorer/answers.json"))
    assert actual == (public_sha, private_sha)
    assert tuple(scene["height_m"] for _, scene in metadata_only) == heights


def test_mixed_height_band_is_independent_of_site_order_hemisphere_and_edge():
    orientations = set()
    for value in range(64):
        seed = value.to_bytes(32, "big")
        ranges = panel.mixed_height_ranges(seed)
        assert ranges == panel.mixed_height_ranges(seed)
        assert set(ranges) == {(25., 110.), (1000., 2500.)}
        layout = holdout_geography.fresh_layout(np.random.default_rng(value))
        for index, ((coordinate, edge), band) in enumerate(zip(layout, ranges, strict=True)):
            orientations.add((index, coordinate[0] > 0, edge, band[0] >= 1000))
    assert len(orientations) == 16


def test_mixed_height_requires_fresh_mode_before_creating_outputs(tmp_path):
    root = tmp_path / "historical"
    with pytest.raises(ValueError, match="fresh-site"):
        panel.generate(root, SEED, mixed_height=True)
    assert not root.exists()


def test_mixed_height_replays_privately_and_survives_only_into_scoring(metadata_only, tmp_path):
    default, first, replay = (tmp_path / name for name in ("default", "first", "replay"))
    panel.generate(default, SEED, True)
    panel.generate(first, SEED, True, mixed_height=True)
    panel.generate(replay, SEED, True, mixed_height=True)
    private = first / "scorer/answers.json"
    assert private.parent.stat().st_mode & 0o077 == 0
    assert private.read_bytes() == (replay / "scorer/answers.json").read_bytes()
    public = first / "public/panel.json"
    assert public.read_bytes() == (replay / "public/panel.json").read_bytes()
    document = json.loads(public.read_bytes())
    default_doc = json.loads((default / "public/panel.json").read_bytes())
    assert set(document) == {"jobs", "inputs", "commitment", "geography_protocol"}
    assert document["commitment"] == hashlib.sha256(private.read_bytes()).hexdigest()
    assert document["commitment"] != default_doc["commitment"]
    assert {k: v for k, v in document.items() if k != "commitment"} == {
        k: v for k, v in default_doc.items() if k != "commitment"
    }
    assert all(set(job) == {"recording", "offer"} for job in document["jobs"])
    assert len(document["jobs"]) == 8
    for job in document["jobs"]:
        offer = first / "public" / (job["offer"] + ".json")
        assert set(json.loads(offer.read_bytes())) == {"center", "width_km"}
    assert all(b"height" not in p.read_bytes() for p in (first / "public").rglob("*.json"))

    low, high = sorted(scene["height_m"] for _, scene in metadata_only[2:4])
    assert 25 <= low <= 110 and 1000 <= high <= 2500
    assert [edge for edge, _ in metadata_only[:2]] == [edge for edge, _ in metadata_only[2:4]]
    truth = json.loads(private.read_bytes())
    assert {answer["height_m"] for answer in truth["answers"].values()} == {low, high}
    heights = {tuple(answer["truth"]): answer["height_m"] for answer in truth["answers"].values()}
    prediction = lock(public, hashlib.sha256(public.read_bytes()).hexdigest(), "candidate", tmp_path)
    assert "height_m" not in json.dumps(prediction)
    revealed = score(prediction, truth)
    for key in ("rows", "by_site"):
        for row in revealed[key]:
            assert row.pop("height_m") == heights[row["site"]]
    for answer in truth["answers"].values():
        del answer["height_m"]
    assert revealed == score(prediction, truth)
