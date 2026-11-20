import pytest

from tools.pipeline_eval.qualification import whole_pressure_trial as trial


def test_release_verification_rejects_additional_changes(tmp_path):
    fitted_source, manifest = sorted(trial.CHANGED)
    reference = {fitted_source: "old code", manifest: "old root", "projector.so": "binary"}
    candidate = {fitted_source: "fixed code", manifest: "new root", "projector.so": "binary"}
    assert trial.release_files(reference, candidate, candidate.copy()) == candidate
    unpinned = dict(candidate, **{"projector.so": "changed binary"})
    with pytest.raises(ValueError):
        trial.release_files(reference, unpinned, unpinned.copy())

    original_path, candidate_path = (tmp_path / name for name in ("original", "candidate"))
    sources = {}
    for name in trial.SOURCES:
        for release in (original_path, candidate_path):
            path = release / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"native compiler input")
        sources[name] = trial._sha(original_path / name)
    assert trial.verify_sources(candidate_path, original_path, sources) == sources
    (candidate_path / sorted(sources)[0]).write_bytes(b"changed compiler input")
    with pytest.raises(ValueError):
        trial.verify_sources(candidate_path, original_path, sources)


def test_exact_raw_support_ignores_runtime_but_rejects_archive_changes():
    authority = {key: f"verified {key}" for key in trial.band.COMMON}
    stock = dict(
        authority,
        dual_calls=6767,
        counts={"candidate_rows": 10, "detector_cpu_s": 10.0},
        input_manifest_sha256="clock",
        detector_sha256="library",
    )
    candidate = dict(stock, counts={"candidate_rows": 10, "detector_cpu_s": 9.8})
    same = {"native_sha256": "same document"}
    assert trial.check_paired_raw(candidate, stock, authority, same, same)
    assert not trial.check_paired_raw({}, stock, authority, {}, same)
    with pytest.raises(ValueError):
        trial.check_paired_raw(candidate, stock, authority, {"native_sha256": "altered"}, same)
    with pytest.raises(ValueError):
        trial.check_paired_raw(
            candidate, stock, dict(authority, probes_sha256="changed"), same, same
        )


def test_scores_keep_both_calibration_arms_and_censored_control():
    historical = dict(status="ok", latlon=[0, 0.01], error_km=1.2)
    reference = dict(
        truth=[0, 0],
        reference={name: dict.fromkeys(trial.ARMS, historical) for name in trial.V5_OPTIONS},
    )
    records = [
        dict(
            method=method,
            result=dict(
                status="failed" if branch == "narrow" else "ok",
                metrics={"c0_frequency_score": 12},
                arms={
                    "c0": {"latlon": [0, 0], "rf_rms_hz": 60}
                    if branch != "narrow"
                    else {"latlon": None},
                    "fitted_c": {"latlon": None},
                },
            ),
        )
        for branch, method in trial.BRANCHES.items()
    ]
    rows = trial.score_rows(records, {"narrow": {"wall_to_failure_s": 10}}, reference)
    assert len(rows) == 14
    for row in (row for row in rows if row["branch"] == "narrow"):
        assert row["status"] == "failed"
        assert row["error_km"] is None
        assert row["wall_to_failure_s"] == 10
        assert row["wall_s"] is None
        assert not row["published"]
    repair = {row["arm"]: row for row in rows if row["branch"] == "repair"}
    assert repair["c0"]["error_km"] == 0
    assert repair["c0"]["conditional_rms_hz"] == 60
    assert repair["c0"]["conditional_frequency_score"] == 12
    assert repair["c0"]["published"] and not repair["fitted_c"]["published"]
