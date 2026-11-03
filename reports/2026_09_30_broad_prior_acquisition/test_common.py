import json
import pytest
from common import digest, independent_tracks, selected_units, seal


def test_shared_selection_has_exactly_same_distinct_recordings():
    units = selected_units()
    assert len(units) == len(set(units)) == 64
    assert [sum(u.startswith(d + "-") for u in units) for d in ("DS9", "DS10", "DS11")] == [22, 21, 21]


def test_overlap_policy_does_not_count_one_source_twice():
    rows = [dict(track_id=str(i), support_start_utc_ns=i, support_end_utc_ns=i+1,
                 measured_hz=[1.,2.,3.], physical_observation_ids=ids)
            for i, ids in enumerate((["a","b","c"], ["c","d","e"], ["f","g","h"]))]
    kept, excluded = independent_tracks({"tracks": rows})
    assert [r["track_id"] for r in kept] == ["0", "2"]
    assert excluded[0]["conflicting_ids"] == ["c"]


def test_sealing_is_immutable(tmp_path):
    path = tmp_path / "fit.json"
    seal(path, {"status": "complete"})
    assert json.loads(path.with_suffix(".seal.json").read_text())["prediction_sha256"] == digest(path)
    with pytest.raises(FileExistsError):
        seal(path, {"status": "changed"})


def test_adapter_does_not_shadow_experiment_launcher():
    import subprocess
    import sys
    from common import HERE, ROOT
    # Exercise a fresh CLI interpreter; other report tests mutate sys.path.
    code = (f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
            "import common, launch; from pathlib import Path; "
            "assert Path(launch.__file__).parent == common.HERE")
    subprocess.run([sys.executable, "-c", code], cwd=HERE, check=True)
