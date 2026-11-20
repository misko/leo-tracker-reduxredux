from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import wide_reference_recovery as trial
from tools.pipeline_eval.qualification import wide_reference_recovery_results as results
from tools.pipeline_eval.qualification.full_receiver_comparison import read, sha


def test_relocation_preserves_every_scientific_request_field(tmp_path):
    request = dict(
        policy="fast-v5-zero-recovery-control-v1",
        source={"files": {"engine.py": "bound"}},
        job=dict(
            native_input={"path": "/old/native.json", "sha256": "native"},
            track_config={"path": "/old/config.json", "sha256": "track"},
            tle_root="/old/tle",
            output_root="/old/result",
            evaluation_reference=None,
            execution_policy={"keep_all_late_stages": True},
        ),
    )
    moved = trial.relocated(request, tmp_path)
    restored = deepcopy(moved)
    restored["job"]["native_input"]["path"] = "/old/native.json"
    restored["job"]["track_config"]["path"] = "/old/config.json"
    restored["job"].update(tle_root="/old/tle", output_root="/old/result")
    assert restored == request
    assert moved["job"]["output_root"] == str(tmp_path / "lean-output")


def test_staging_copies_original_provider_hierarchy_before_lock(tmp_path, monkeypatch):
    original, original_report, report = [tmp_path / p for p in ("in", "primary", "repeat")]
    for folder in (original, original_report, report):
        folder.mkdir()
    (report / "PROTOCOL.md").write_text("Two frozen cases.\n")
    pins = {}
    for ident in trial.CASES:
        source = original / ident
        source.mkdir()
        for p in ("native.json", "track-config.json"):
            (source / p).write_text("{}\n")
        tle = source / "tle/archive/space-track/1234-elements.tle"
        tle.parent.mkdir(parents=True)
        tle.write_text("frozen orbit elements\n")
        request = dict(
            role="baseline",
            source={"sha256": trial.bound.v5.SOURCE_SHA256},
            causal_snapshots={tle.name: sha(tle)},
            job=dict(
                evaluation_reference=None,
                output_root="/old/out",
                tle_root=str(source / "tle"),
                native_input={
                    "path": str(source / "native.json"),
                    "sha256": sha(source / "native.json"),
                },
                track_config={
                    "path": str(source / "track-config.json"),
                    "sha256": sha(source / "track-config.json"),
                },
            ),
        )
        save_json(source / "request.json", request)
        pins[ident] = dict(
            rebound_request_sha256=sha(source / "request.json"),
            original_native_sha256="era",
            compact=dict(catalog_sha256="causal", tile={"id": "original"}),
        )
    save_json(original_report / "source-lock.json", {"cases": pins})
    save_json(
        original / "launch-lock.json", {"source_sha256": sha(original_report / "source-lock.json")}
    )
    monkeypatch.setattr(trial, "REPORT", report)
    monkeypatch.setattr(trial.bound, "REPORT", original_report)
    monkeypatch.setattr(trial.bound, "WORK", original)
    monkeypatch.setattr(trial.bound.original_v5, "RUNNER_DIGESTS", {})
    work = tmp_path / "work"
    trial.prepare(work)
    assert (work / "study.sha256").read_text().strip() == sha(report / "source-lock.json")
    for ident in trial.CASES:
        request = read(work / ident / "request.json")
        tle = Path(request["job"]["tle_root"]) / "archive/space-track/1234-elements.tle"
        assert sha(tle) == request["causal_snapshots"][tle.name]
        assert request["job"]["evaluation_reference"] is None
    bad = original / trial.CASES[0] / "native.json"
    with pytest.raises(ValueError, match="differs"):
        trial.copy_bound(bad, tmp_path / "corrupt", "0" * 64)


def test_signed_original_recovery_controls_and_scores_reproduce_offline(tmp_path):
    data = results.score(trial.REPORT, tmp_path)
    assert data["DS26-0122"]["primary_status"] == "timed_out"
    assert data["DS26-0122"]["lean_status"] == "ok"
    assert all(
        arm["same_conditional_rms"]
        and arm["same_coordinates"]
        and arm["same_frequency_score"]
        and arm["same_associated_observations"]
        for arm in data["DS29-0082"]["arms"].values()
    )
    for name in ("scores.csv", "parity.json"):
        assert (tmp_path / name).read_bytes() == (trial.REPORT / name).read_bytes()
