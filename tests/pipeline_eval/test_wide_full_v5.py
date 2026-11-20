from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import wide_full_v5 as trial
from tools.pipeline_eval.qualification import wide_full_v5_results as results


def test_confirmation_selection_uses_complete_factor_digest():
    rows = {
        ident: dict(native_sha256=value, score=outcome)
        for ident, value, outcome in (
            ("DS26-0122", "00", 1),
            ("DS29-0082", "00", 2),
            ("DS26-A", "cc", 0),
            ("DS26-B", "aa", 10),
            ("DS29-A", "bb", 11),
            ("DS29-B", "ff", 0),
        )
    }
    assert trial.ranking(rows) == ["DS26-0122", "DS29-0082", "DS26-B", "DS29-A"]


def test_request_changes_only_factor_identity_and_output_path(tmp_path):
    case = dict(
        id="DS26-0122",
        session_id="same-session",
        native={"sha256": "aa"},
        request={"sha256": "request"},
        catalog={"sha256": "ca"},
        regions=[{"id": "original"}],
    )
    original = dict(
        role="baseline",
        policy="fast-v5-zero-recovery-control-v1",
        source={"sha256": "engine"},
        native_manifest={"compiler": "original"},
        causal_snapshots={"tle": "orbit"},
        job=dict(
            evaluation_reference=None,
            identity={"session_id": "same-session"},
            native_input={"path": "/old", "sha256": "sha256:aa"},
            output_root="/old-output",
            track_config={"sha256": "track"},
            screen_center=[1, 2],
            search_center=[3, 4],
        ),
    )
    original["job"]["identity"].update(
        input_sha256="sha256:aa", run_id=trial._run_id(original, case["id"], "sha256:aa")
    )
    blob = b"complete wide factors"
    wide = dict(
        native_sha256=sha256(blob).hexdigest(),
        original_request_sha256="request",
        catalog_sha256="ca",
        tile={"id": "original"},
    )
    bound = trial.bind(original, case, wide, blob, tmp_path)
    assert bound["job"]["native_input"]["sha256"] == "sha256:" + sha256(blob).hexdigest()
    assert bound["job"]["native_input"]["path"] == str(tmp_path / "native.json")
    normalized = deepcopy(bound)
    for key in ("identity", "native_input", "output_root"):
        normalized["job"][key] = original["job"][key]
    assert normalized == original
    with pytest.raises(ValueError):
        trial.bind(original, case, wide, b"changed factors", tmp_path)
    original["job"]["evaluation_reference"] = [0, 0]
    with pytest.raises(ValueError):
        trial.bind(original, case, wide, blob, tmp_path)


def test_failed_full_fit_stays_in_both_calibration_denominators():
    ident = "DS29-0082"
    refs = {
        ident: dict(
            truth=[0, 0],
            reference={
                role: {arm: dict(latlon=[0, 1], error_km=111, status="fix") for arm in results.ARMS}
                for role in results.V5_OPTIONS
            },
        )
    }
    records = [
        dict(
            id=ident,
            method=method,
            result=dict(
                metrics={}, status=status, arms={arm: {"latlon": point} for arm in results.ARMS}
            ),
        )
        for method, status, point in (
            (results.FULL, "timed_out", None),
            (results.COMPACT, "ok", [0, 0]),
        )
    ]
    scores = results.score_rows(records, refs, {ident: {"full": {"wall_s": 600}, "compact": {}}})
    assert len(scores) == 12
    misses = [r for r in scores if r["method"] == results.FULL]
    assert {r["arm"] for r in misses} == set(results.ARMS)
    assert all(not r["published"] and not r["within_10pct"] for r in misses)
    assert all(r["original_full_minus_compact_wide_km"] is None for r in misses)


def test_actual_manager_counters_are_preserved_when_worker_was_killed(tmp_path):
    state = dict(
        MainPID="0",
        ControlPID="0",
        ActiveEnterTimestampMonotonic="1000000",
        InactiveEnterTimestampMonotonic="602000000",
        CPUUsageNSec="205000000000",
        MemoryPeak="4070000000",
    )
    actual = results.run_resources(tmp_path, {"systemd": state})
    assert actual["cap_bytes"] == 4 * 1024**3
    assert actual["wall_s"] == 601
    assert actual["cpu_s"] == 205
    assert actual["peak_bytes"] == 4_070_000_000
