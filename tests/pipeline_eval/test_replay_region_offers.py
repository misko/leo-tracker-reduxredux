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
