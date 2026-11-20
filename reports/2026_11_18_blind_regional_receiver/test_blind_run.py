import json
import subprocess
import sys
from importlib import import_module

import pytest

runner = import_module("reports.2026_11_18_blind_regional_receiver.run_study")
worker = import_module("reports.2026_11_18_blind_regional_receiver.blind_worker")


def test_one_case_in_namespace(tmp_path):
    obs = dict(anchor_utc_ns=0, cutoff_utc_ns=5_000_000_000, catalog_timestamp_ns=0,
               duration_s=5.0, tracks=[])
    data = runner.packed(obs)
    tle = b""
    query = dict(id="toy", observation=runner.sha(data), catalog=runner.sha(tle),
                 regions=[dict(id=str(i), center=[i, i]) for i in range(4)])
    paths = {}
    for name, contents in (("query.json", runner.packed(query)), ("observation.json", data),
                           ("orbits.tle", tle)):
        path = tmp_path / name
        path.write_bytes(contents)
        paths[name] = path
    output = runner.dispatch(paths, "primary")
    assert (output["status"], output["region_id"], output["latlon"]) == ("withheld", None, None)
    assert output["reason"] == "insufficient_tracks"
    paths["orbits.tle"].write_bytes(b"modified")
    with pytest.raises(RuntimeError, match="fingerprint mismatch"):
        runner.dispatch(paths, "primary")


def test_ids_and_publication_schema(tmp_path):
    with pytest.raises(ValueError, match="ID"):
        runner.one_query(tmp_path, "../truth")
    result = dict(status="withheld", reason="test", region_id=None, latlon=[0, 0],
                  best_region=None, best_latlon=None)
    with pytest.raises(ValueError, match="withheld"):
        worker.validate_result(result, [])


def test_invariance_queries_independent_of_manifest_order():
    ids = [f"item_{i}" for i in range(20)]
    chosen = runner.jobs_for(ids, controls=True)
    assert len(chosen) == 9
    assert chosen == runner.jobs_for(list(reversed(ids)), controls=True)
    assert len({qid for qid, _ in chosen}) == 3


def test_user_cli_withholds_and_omits_forced_diagnostics(tmp_path):
    obs, cat, offers = (tmp_path / x for x in ("obs", "tle", "regions"))
    obs.write_text(json.dumps({"duration_s": 5, "tracks": []}))
    cat.write_text("")
    offers.write_text(json.dumps([{"id": "a", "center": [1, 2]}]))
    args = [sys.executable, str(runner.ROOT / "predict_one.py"), "--observation", str(obs),
            "--catalog", str(cat), "--regions", str(offers)]
    answer = json.loads(subprocess.check_output(args))
    assert answer == dict(status="withheld", reason="insufficient_tracks", region_id=None,
                          latlon=None)
