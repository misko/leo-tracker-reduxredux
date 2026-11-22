from importlib import import_module
from pathlib import Path

import pytest


trial = import_module("reports.ALGO08.single-core-2x.replay_region_offers")


@pytest.mark.parametrize("failure", [None, "owner", "rf", "archive", "duplicate"])
def test_offer_replay_binds_original_and_changed_regions_without_truth(tmp_path, monkeypatch, failure):
    pair, spec, changed, output = [tmp_path / name for name in ("pair", "spec", "offer", "out")]
    trial.write(pair, {})
    trial.write(spec, {"solver": "test"})
    digest = trial.canonical_digest(trial.read(spec))
    center = {"center": [-35., 114.], "width_km": 25.}
    anchor = trial.Algo08Region.parse(center).document()
    other = center if failure == "duplicate" else dict(center, center=[-36., 115.])
    trial.write(changed, other)
    history = {"snapshots_sha256": "pinned"}
    obs = {"raw": "saved measurements"}
    original = {"arms": {"c0": {"latlon": [-35., 114.], "rf_rms_hz": 2.}}, "owners": {"c0": "satellites"},
                "raw_authority": "raw"}
    monkeypatch.setattr(trial, "saved_inputs", lambda *args, **kw:
                        ({"archive": history}, original, spec, tmp_path, anchor, obs))
    monkeypatch.setattr(trial, "archive_identity", lambda path: {} if failure == "archive" else history)
    monkeypatch.setenv("ALGO08_EVALUATION_LATITUDE", "unused-reference")
    seen = []

    def solve(cmd, *, env, **kwargs):
        assert "ALGO08_EVALUATION_LATITUDE" not in env
        assert trial.read(Path(cmd[-5])) == obs
        seen.append(trial.read(Path(cmd[-2])))
        result = {"status": "ok", "arms": original["arms"], "owners": original["owners"]}
        if failure == "owner":
            result["owners"] = {"c0": "other satellite"}
        if failure == "rf":
            result["arms"] = {"c0": dict(original["arms"]["c0"], rf_rms_hz=3.)}
        trial.write(Path(cmd[-1]), result)

    monkeypatch.setattr(trial.subprocess, "run", solve)
    if failure:
        with pytest.raises(ValueError):
            trial.replay(pair, tmp_path, digest, [changed], output)
        assert not output.exists()
        if failure == "duplicate":
            assert not seen
    else:
        trial.replay(pair, tmp_path, digest, [changed], output)
        result = trial.read(output)
        assert result["candidate_specification_digest"] == digest
        assert result["native_sha256"] == trial.canonical_digest(obs)
        assert result["archive"] == history
        assert [row["region"] for row in result["results"]] == seen == [
            anchor, trial.Algo08Region.parse(other).document()]


@pytest.mark.parametrize("failure", [None, "wrong-launcher", "different-waveform"])
def test_deployed_replay_uses_its_bound_release_and_own_measurements(tmp_path, monkeypatch, failure):
    pair, spec, changed, output = [tmp_path / name for name in ("pair", "spec", "offer", "out")]
    trial.write(pair, {})
    trial.write(spec, {"solver": "test"})
    digest = trial.canonical_digest(trial.read(spec))
    anchor = trial.Algo08Region.parse(dict(center=[-35., 114.], width_km=25.)).document()
    trial.write(changed, dict(center=[-36., 114.5], width_km=25.))
    history = {"snapshots_sha256": "pinned"}
    candidate = {"raw_authority": "raw"}
    baseline = dict(
        launcher=str((tmp_path if failure == "wrong-launcher" else trial.RELEASE) / "run"),
        raw_authority="different" if failure == "different-waveform" else "raw",
        receipt=dict(decision="complete", region=anchor),
        arms={"c0": {"latlon": [-35., 114.], "rf_rms_hz": 2.}}, owners={"c0": "stock"},
    )
    publication = dict(archive=history, runs=dict(baseline=baseline))
    monkeypatch.setattr(trial, "saved_inputs", lambda *args, **kw:
                        (publication, candidate, spec, tmp_path, anchor, {"detector": "candidate"}))
    monkeypatch.setattr(trial, "archive_identity", lambda path: history)
    observed, calls = {"detector": "deployed"}, []

    def detections(path, method, row):
        assert path == pair and method == "baseline" and row is baseline
        return observed

    def solve(cmd, *, env, **kwargs):
        assert "--deployed-worker" in cmd
        assert str(spec) not in cmd
        assert env["PYTHONPATH"].split(":")[:2] == [str(trial.RELEASE / "src"), str(trial.RELEASE)]
        assert trial.read(Path(cmd[-4])) == observed
        calls.append(trial.read(Path(cmd[-2])))
        trial.write(Path(cmd[-1]), dict(status="ok", arms=baseline["arms"], owners=baseline["owners"]))

    monkeypatch.setattr(trial, "saved_native", detections)
    monkeypatch.setattr(trial.subprocess, "run", solve)
    if failure:
        with pytest.raises(ValueError, match="Expected the original deployed publication"):
            trial.replay(pair, tmp_path, digest, [changed], output, method="baseline")
        assert not calls and not output.exists()
    else:
        trial.replay(pair, tmp_path, digest, [changed], output, method="baseline")
        result = trial.read(output)
        assert result["method"] == "baseline"
        assert result["native_sha256"] == trial.canonical_digest(observed)
        assert [row["region"] for row in result["results"]] == calls == [
            anchor, trial.Algo08Region.parse(trial.read(changed)).document()]
