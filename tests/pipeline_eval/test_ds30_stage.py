from importlib import import_module
import json
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest


stage = import_module("reports.ALGO08.single-core-2x.ds30_stage")
pair = stage.pair
REGION = dict(center=[37.906, -122.545], screen_center=[37.5, -122.0], width_km=25.0)
ARMS = {arm: {"latlon": None} for arm in ("c0", "fitted_c")}


@pytest.fixture
def study(tmp_path):
    archive = tmp_path / "tle"
    archive.mkdir()
    candidate = tmp_path / "candidate"
    region = tmp_path / "offer.json"
    region.write_text(json.dumps(REGION))
    corpus = []
    for index in range(1, 5):
        case = f"DS30-{index:04d}"
        corpus.append(stage.Assignment(case, index, tmp_path / f"wave-{index}", REGION, archive,
                                       pair.archive_identity(archive)["snapshots_sha256"], f"session-{index}",
                                       canonical_digest(index), 1, 0))
    return SimpleNamespace(runs=tmp_path / "runs", assignments=corpus, candidate=candidate,
                           region=region, spec=dict(detector_sha256="b" * 64))


def seal_pair(study, entry, elapsed=(4., 1.), *, archived=True):
    directory = study.runs / entry.name
    directory.mkdir(parents=True)
    data = dict(order=entry.order, cpu=2, recording=str(entry.recording), region=str(study.region),
                candidate_specification=study.spec, candidate_specification_digest=canonical_digest(study.spec),
                runs={}, elapsed_ratio=elapsed[1] / elapsed[0])
    if archived:
        data["archive"] = pair.archive_identity(entry.archive)
    pair.immutable_json(directory / "candidate-config.json", study.spec)
    for label, launcher, timing, detector in zip(
        ("baseline", "candidate"), (pair.BASELINE, study.candidate), elapsed,
        (stage.BASELINE_DETECTOR, "sha256:" + study.spec["detector_sha256"]), strict=True,
    ):
        root = directory / label
        scans = pair.FastScanStore(root)
        publications = pair.FastStandardAnalysisStore(root)
        run = "algo08-v2-" + entry.name.lower()
        native = dict(source=dict(probes=[], raw_recording_authority_digest=entry.raw_authority),
                      provenance=dict(detector_sha256=detector))
        pair.immutable_json(scans.automatic_workspace("detector") / "detections.json", native)
        terminal = dict(region=REGION, reason="no probes", arms=ARMS, native_sha256=canonical_digest(native))
        terminal_sha = canonical_digest(terminal)
        pair.immutable_json(scans.automatic_workspace(run) / "terminal.json", terminal)
        scans.publish(run, dict(session_id=entry.session, points=[]))
        publications.withhold(run, terminal["reason"], terminal_sha256=terminal_sha,
                              region=REGION, raw_authority=entry.raw_authority)
        receipt = dict(run_id=run, session_id=entry.session, window_count=entry.windows,
                       counts=dict(processed=0, invalid_capture=1, skipped_fast_score=0),
                       region=REGION, decision="withheld", terminal_sha256=terminal_sha)
        measured = pair.evidence(root, receipt, 0)
        measured["terminal_file_s"] = timing / 2
        data["runs"][label] = dict(measured, launcher=str(launcher), elapsed_s=timing, cpu_s=timing)
    path = directory / "pair.json"
    pair.immutable_json(path, data)
    return path


def inventory(study):
    return stage.inventory(study.runs, study.assignments, study.candidate, study.spec, 2)


def test_one_case_and_frozen_order_without_launching_a_benchmark(study, monkeypatch):
    first, second, *_ = study.assignments
    calls = []
    monkeypatch.setattr(pair, "run_pair", calls.append)
    original = inventory(study)
    assert not study.runs.exists()
    with pytest.raises(ValueError, match=first.name):
        stage.next_case(original, second.name)
    launch = lambda snapshot, requested: stage.run_next(study.runs, study.assignments, snapshot, requested,
                                                        study.candidate, study.region, study.region)
    launch(original, None)
    assert len(calls) == 1 and calls[0].recording == first.recording and calls[0].first == "candidate"
    assert calls[0].archive_inventory_sha256 == first.snapshots_sha256
    seal_pair(study, first)
    current = inventory(study)
    assert current["coverage"]["verified"] == [first.name]
    assert stage.score(current)["elapsed_gates"] is None
    with pytest.raises(ValueError, match=second.name):
        launch(current, first.name)
    launch(current, second.name)
    assert len(calls) == 2 and calls[1].recording == second.recording and calls[1].first == "baseline"


def test_legacy_audit_has_no_qualification_coverage(study):
    first = study.assignments[0]
    seal_pair(study, first, archived=False)
    state = stage.score(inventory(study))
    assert state["coverage"]["development"] == [first.name]
    assert state["cases"][0]["audit_sha256"].startswith("sha256:")
    assert state["elapsed_gates"] is None
    with pytest.raises(ValueError, match="unqualified attempt"):
        stage.next_case(state, None)


@pytest.mark.parametrize("changed", ["recording", "region", "order", "cpu", "archive", "candidate_specification_digest",
                                     "launcher", "raw_authority", "paired_native"])
def test_stale_swapped_or_unbound_pair_is_explicitly_invalid(study, changed):
    first, second, *_ = study.assignments
    path = seal_pair(study, first)
    data = stage.read(path)
    wrong_offer = study.region.with_name("wrong.json")
    wrong_offer.write_text(json.dumps(dict(REGION, screen_center=[-30., 16.])))
    replacements = dict(recording=str(second.recording), region=str(wrong_offer),
                        order=second.order, cpu=3, archive=dict(root="different"),
                        candidate_specification_digest="sha256:"+"0"*64)
    if changed in replacements:
        data[changed] = replacements[changed]
    elif changed == "paired_native":
        files = list((path.parent / "candidate").glob("*/detector/detections.json"))
        files[0].write_text(json.dumps(dict(source=dict(probes=["changed"]))))
    else:
        data["runs"]["baseline"][changed] = "wrong"
    path.write_text(json.dumps(data))
    state = inventory(study)
    assert state["coverage"]["invalid"] == [first.name]
    assert stage.score(state)["elapsed_gates"] is None
    with pytest.raises(ValueError, match="unqualified attempt"):
        stage.next_case(state, None)


def test_failed_or_incomplete_attempts_cannot_be_skipped(study):
    first, second, *_ = study.assignments
    path = study.runs / first.name / "pair.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"failure":"timeout during solve"}')
    (study.runs / second.name).mkdir()
    state = inventory(study)
    assert state["coverage"]["failed"] == [first.name, second.name]
    assert state["cases"][0]["reason"] == "timeout during solve"
    with pytest.raises(ValueError, match="unqualified attempt"):
        stage.next_case(state, None)


def test_read_only_verifier_does_not_recreate_missing_terminal_workspace(study):
    first = study.assignments[0]
    path = seal_pair(study, first)
    run = stage.read(path)["runs"]["baseline"]["receipt"]["run_id"]
    terminal_workspace = pair.FastScanStore(path.parent / "baseline").automatic_workspace(run)
    terminal_workspace.rename(terminal_workspace.with_name("missing-terminal"))
    assert inventory(study)["coverage"]["invalid"] == [first.name]
    assert not terminal_workspace.exists()


def test_verified_receipt_requires_current_causal_inventory(study):
    first = study.assignments[0]
    seal_pair(study, first)
    changed = first.archive / "archive/space-track" / ("1794834194832608864-"+"a"*64+".tle")
    changed.parent.mkdir(parents=True)
    changed.touch()
    state = inventory(study)
    assert state["coverage"]["invalid"] == [first.name]
    assert "causal archive" in state["cases"][0]["reason"]


def test_pair_records_archive_identity_and_records_a_changed_inventory_as_failure(study, monkeypatch):
    first = study.assignments[0]
    original_archive = pair.archive_identity(first.archive)
    monkeypatch.setattr(pair, "LOCK", study.runs.parent / "gauss.lock")
    monkeypatch.setattr(pair.os, "sched_getaffinity", lambda _: {2})
    monkeypatch.setattr(pair.os, "sched_setaffinity", lambda *args: None)
    monkeypatch.setattr(pair.os, "setpriority", lambda *args: None)
    monkeypatch.setattr(pair.subprocess, "run", lambda *args, **kwargs: None)

    def measure(launcher, *args):
        if launcher == pair.BASELINE:
            changed = first.archive / "archive/space-track" / ("1794834194832608864-" + "a" * 64 + ".tle")
            changed.parent.mkdir(parents=True)
            changed.touch()
        return dict(raw_authority=first.raw_authority, elapsed_s=1.,
                    receipt=dict(region=first.region, session_id=first.session, window_count=1))

    monkeypatch.setattr(pair, "measure", measure)
    args = SimpleNamespace(cpu=2, output=study.runs / first.name, recording=first.recording,
                           archive=first.archive, archive_inventory_sha256=first.snapshots_sha256,
                           region=study.region, first=first.order[0], baseline=pair.BASELINE,
                           candidate=study.candidate, blind_panel=None, candidate_config=None)
    with pytest.raises(ValueError, match="changed during the pair"):
        pair.run_pair(args)
    recorded = stage.read(args.output / "pair.json")
    assert recorded["archive"] == original_archive
    assert "changed during the pair" in recorded["failure"] and "elapsed_ratio" not in recorded


def test_stage_build_binds_candidate_config_and_all_binary_pins(tmp_path, monkeypatch):
    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"frozen candidate")
    baseline = tmp_path / "baseline"
    baseline.write_bytes(b"frozen baseline")
    library = tmp_path / "detector.so"
    library.write_bytes(b"frozen detector")
    monkeypatch.setattr(pair, "BASELINE", baseline)
    monkeypatch.setattr(stage, "BASELINE_SHA256", stage.file_sha(baseline))
    spec = dict(sources={candidate.name: stage.file_sha(candidate)},
                detector=str(library), detector_sha256=stage.file_sha(library))
    config = tmp_path / "spec.json"
    config.write_text(json.dumps(spec))
    expected = canonical_digest(spec)
    assert stage.verify_build(candidate, config, expected) == spec
    with pytest.raises(ValueError, match="supplied digest"):
        stage.verify_build(candidate, config, "0" * 64)
    library.write_bytes(b"changed detector")
    with pytest.raises(ValueError, match="Frozen candidate binary changed"):
        stage.verify_build(candidate, config, expected)


def test_full_stage_only_scores_both_elapsed_gates_and_keeps_withholds(study, monkeypatch):
    monkeypatch.setattr(stage, "pinned", lambda *args: dict(cases=[
        dict(dataset_label=a.name, authority_eligible=True, reference=dict(latitude_deg=1., longitude_deg=2.))
        for a in study.assignments]))
    for entry, times in zip(study.assignments, ((4., 1.), (4., 1.), (4., 1.), (100., 99.)), strict=True):
        seal_pair(study, entry, elapsed=times)
    result = stage.score(inventory(study))
    assert result["elapsed_gates"]["median_pass"]
    assert not result["elapsed_gates"]["summed_pass"] and not result["elapsed_gates"]["passed"]
    assert result["position"]["candidate"]["c0"]["assigned"] == 4
    assert result["position"]["candidate"]["c0"]["error_km"]["n"] == 0
