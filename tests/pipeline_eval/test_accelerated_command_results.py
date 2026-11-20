import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import accelerated_command_results as results


def test_original_v5_scores_keep_both_timeout_arms_without_positions(monkeypatch, tmp_path):
    monkeypatch.setattr(results, "V5_ARCHIVE", tmp_path)
    case = "DS26-test"
    directory = tmp_path / f"{case}-r0"
    reference = dict(truth=[38, -123], reference={})
    for role in results.ROLES:
        path = directory / role / "experimental-request.json"
        path.parent.mkdir(parents=True)
        request = dict(
            role=role,
            source={"sha256": "release"},
            causal_snapshots={"12-current.tle": "sha256:current", "51-later.tle": "sha256:later"},
            job=dict(
                identity={"session_id": "capture"},
                evaluation_reference=None,
                native_input={"sha256": "sha256:native"},
                search_center=[38, -123],
            ),
        )
        path.write_bytes(encoded(request))
        digest = "sha256:" + results._sha(path)
        timed_out = role == "omitted-tracks"
        execution = dict(
            role=role,
            request_sha256=digest,
            status="timed_out" if timed_out else "complete",
            timeout_seconds=1200,
            process={"wall_seconds": 1200.4 if timed_out else 40},
        )
        point, rms = (None, None) if timed_out else ([38, -123], 72.0)
        if not timed_out:
            execution["worker"] = dict(
                request_sha256=digest,
                arms={a: dict(endpoint_latlon=point, residual_rms_hz=rms) for a in results.ARMS},
            )
        reference["reference"][role] = {
            a: dict(status="timed_out" if timed_out else "fix", latlon=point, rf_rms_hz=rms)
            for a in results.ARMS
        }
        (directory / f"{role}-execution.json").write_bytes(encoded(execution))
    item = dict(
        id=case,
        native={"sha256": "native"},
        request={"sha256": results._sha(directory / "baseline/experimental-request.json")},
        regions=[{"center": [38, -123]}],
        session_id="capture",
        cutoff_utc_ns=40,
        catalog_timestamp_ns=12,
        catalog={"sha256": "current"},
    )
    rows, receipt = results.original_v5_scores(item, reference)
    assert len(rows) == 8
    missing = [r for r in rows if r["method"] == "omitted-tracks"]
    assert [r["arm"] for r in missing] == list(results.ARMS)
    assert all(r["status"] == "timed_out" for r in missing)
    assert all(r["error_km"] is None and r["rf_rms_hz"] is None for r in missing)
    assert receipt["omitted-tracks"]["wall_s"] == 1200.4
    assert [r["rf_rms_hz"] for r in rows if r["status"] == "ok"] == [72.0] * 6

    reference["reference"]["omitted-tracks"]["c0"]["latlon"] = [38, -123]
    with pytest.raises(ValueError, match="differs from the official frozen scores"):
        results.original_v5_scores(item, reference)
