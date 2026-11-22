from importlib import import_module
from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import ALGO08V2, PLOTS


stage = import_module("reports.ALGO08.single-core-2x.ds30_stage")
pair = stage.pair
REGION = dict(center=[37.906, -122.545], screen_center=[37.5, -122.0], width_km=25.0)
ARMS = {arm: {"latlon": None} for arm in ("c0", "fitted_c")}


def test_only_reviewed_covariance_build_uses_full_scan_comparison():
    path = stage.PANEL.parents[1] / "single-core-2x/measurements/covariance-posterior-freeze.json"
    spec = stage.read(path)["spec"]
    assert stage.comparison_mode(spec) == "full-scan-signed"
    with pytest.raises(ValueError, match="frozen full-scan"):
        stage.comparison_mode(dict(spec, regional_veto=False))


def test_only_frozen_screened_tiled_build_uses_scientific_comparison():
    path = stage.PANEL.parents[1] / "single-core-2x/measurements/screened-tiled-freeze.json"
    spec = stage.read(path)["spec"]
    assert stage.comparison_mode(spec) == "full-scan-screened"
    with pytest.raises(ValueError, match="frozen screened-tiled"):
        stage.comparison_mode(dict(spec, schedule="alternate"))


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
                                       canonical_digest(index), 1, 1))
    return SimpleNamespace(runs=tmp_path / "runs", assignments=corpus, candidate=candidate,
                           region=region, spec=dict(detector_sha256="b" * 64))


@pytest.fixture(params=("conditional-residual", "full-scan-signed"))
def conditional_study(study, monkeypatch, request):
    if request.param == "conditional-residual":
        study.spec["schedule"] = "conditional-residual"
        pin = "CONDITIONAL_RESIDUAL"
    else:
        study.spec.update(schedule="all", solver="collapsed-signed")
        pin = "FULL_PHASE_SIGNED"
    monkeypatch.setattr(stage, pin, canonical_digest(study.spec))
    return study


def publish_fix(publications, run, binding, endpoints, offsets, factor_count):
    def png(pixel):
        output = BytesIO()
        Image.new("RGBA", (1, 1), (pixel, 0, 0, 255)).save(output, format="PNG")
        return output.getvalue()

    region = binding["region"]
    center = region["center"]
    frame = dict(region_center=center, box_width_km=region["width_km"])
    grid = dict(frame, schema_version=1, kind="conditional-position-grid", matched_c_grid=True,
                conditioning="published satellite ownership and phase linearization fixed",
                endpoint_latlon=endpoints, evaluated_points=1, planned_points=1, complete=True,
                points=[dict(east_km=0, north_km=0, latlon=center,
                             scores={arm: factor_count for arm in ARMS})])
    path = dict(frame, schema_version=2, kind="recorded-position-path", selected_model=ALGO08V2,
                stages=[dict(model_version=ALGO08V2, arms={arm: dict(endpoint=[0, offsets[arm]],
                            history_available=False, rounds=[]) for arm in ARMS})])
    manifest = dict(binding, run_id=run, schema_version=3, model_version=ALGO08V2, state="complete",
                    selected_model=ALGO08V2, reference_usage="evaluation_only", glrt_points=factor_count,
                    arms={arm: dict(endpoint_latlon=point, associated_points=factor_count,
                                    owner_sha256=canonical_digest(point)) for arm, point in endpoints.items()})
    images = dict.fromkeys(PLOTS, png(1))
    images["position"] = png(factor_count)
    publications.publish(run, manifest, images, position_grid=grid, position_path=path)


def seal_pair(study, entry, elapsed=(4., 1.), *, archived=True, fixes=None):
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
        offsets = (fixes or {}).get(label)
        probes = []
        if offsets is not None:
            factors = [{"cfo_hz": 10}] if label == "candidate" else [{"cfo_hz": 10}, {"cfo_hz": 20}]
            probes = [dict(visit_index=0, receiver_id=0, channel=1, actual_rf_hz=10_000_000_000,
                           valid_start_counter=1000, candidates=factors)]
        native = dict(source=dict(probes=probes, session_id=entry.session,
                                  raw_recording_authority_digest=entry.raw_authority),
                      provenance=dict(detector_sha256=detector))
        pair.immutable_json(scans.automatic_workspace("detector") / "detections.json", native)
        lat, lon = entry.region["center"]
        endpoints = {arm: None if offsets is None else [lat+offsets[arm]/111, lon] for arm in ARMS}
        terminal = dict(region=entry.region, reason="no probes" if offsets is None else None,
                        arms={arm: dict(latlon=point) for arm, point in endpoints.items()},
                        decision="withheld" if offsets is None else "ok", session_id=entry.session,
                        native_sha256=canonical_digest(native))
        terminal_sha = canonical_digest(terminal)
        pair.immutable_json(scans.automatic_workspace(run) / "terminal.json", terminal)
        scans.publish(run, dict(session_id=entry.session, points=[]))
        binding = dict(terminal_sha256=terminal_sha, region=entry.region, raw_authority=entry.raw_authority,
                       session_id=entry.session, input_sha256=terminal["native_sha256"])
        if offsets is None:
            publications.withhold(run, terminal["reason"], **binding)
        else:
            publish_fix(publications, run, binding, endpoints, offsets, len(factors))
        receipt = dict(run_id=run, session_id=entry.session, window_count=entry.windows,
                       counts=dict(processed=entry.visits, invalid_capture=entry.windows-entry.visits,
                                   skipped_fast_score=0),
                       region=entry.region, decision="withheld" if offsets is None else "complete",
                       terminal_sha256=terminal_sha)
        measured = pair.evidence(root, receipt, 0)
        measured["terminal_file_s"] = timing / 2
        data["runs"][label] = dict(measured, launcher=str(launcher), elapsed_s=timing, cpu_s=timing)
    path = directory / "pair.json"
    pair.immutable_json(path, data)
    return path


def inventory(study):
    return stage.inventory(study.runs, study.assignments, study.candidate, study.spec, 2)


def test_timing_diagnostics_keep_missing_counters_out_of_the_zero_read_subset():
    times = {"elapsed_s": {"baseline": 12., "candidate": 3.},
             "cpu_s": {"baseline": 8., "candidate": 4.}, "state": "verified"}
    rows = [dict(times, case="uncounted"), dict(times, case="read", input_blocks={"baseline": 5, "candidate": 0}),
            dict(times, case="warm", input_blocks={"baseline": 0, "candidate": 0}),
            {"case": "unmeasured", "state": "missing"}]
    result = stage.observed_timing(rows)
    assert result["all_verified"]["cases"] == ["uncounted", "read", "warm"]
    subset = result["both_zero_input_blocks"]
    assert subset["cases"] == ["warm"]
    assert subset["elapsed_s"]["summed_candidate_over_baseline"] == .25
    assert subset["cpu_s"]["median_candidate_over_baseline"] == .5
    assert stage.observed_timing(rows[:1])["both_zero_input_blocks"]["cpu_s"]["summed_candidate_over_baseline"] is None


def test_bad_filesystem_counter_invalidates_pair(study):
    first, *_ = study.assignments
    path = seal_pair(study, first)
    data = stage.read(path)
    data["runs"]["candidate"]["input_blocks"] = -1
    path.write_text(json.dumps(data))
    assert inventory(study)["coverage"]["invalid"] == [first.name]


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


def test_stage_passes_only_the_assigned_manifests_and_checks_saved_cache_identity(study, monkeypatch):
    first = study.assignments[0]
    first = replace(first, segment_manifests=((first.recording / "manifest.json", "sha256:" + "b" * 64),))
    study.assignments[0] = first
    calls = []
    helper = study.runs.parent / "helper.so"
    monkeypatch.setattr(pair, "run_pair", calls.append)
    stage.run_next(study.runs, study.assignments, inventory(study), first.name,
                   study.candidate, study.region, study.region, cache_library=helper)
    assert calls[0].cache_library == helper
    assert calls[0].cache_manifests == first.segment_manifests

    path = seal_pair(study, first)
    saved = stage.read(path)
    saved["cache_observation"] = dict(
        method="linux-cachestat", page_size_bytes=4096,
        manifests=pair.cache_residency.manifest_pins(first.segment_manifests),
        arms={arm: dict(cached_pages=None, unavailable={"EPERM": 1}) for arm in stage.BUILDS},
    )
    path.write_text(json.dumps(saved))
    assert inventory(study)["cases"][0]["cache_observation"] == saved["cache_observation"]
    saved["cache_observation"]["manifests"][0]["sha256"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(saved))
    assert inventory(study)["coverage"]["invalid"] == [first.name]


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


def test_separate_workspace_can_preserve_verified_prefix_on_recovery(study):
    first, second, *_ = study.assignments
    seal_pair(study, first)
    failed_directory = study.runs / second.name
    failed_directory.mkdir()
    (failed_directory / "pair.json").write_text('{"failure":"timeout during solve"}')
    original = inventory(study)

    retry_workspace = study.runs.with_name("retry")
    retry_workspace.mkdir()
    (retry_workspace / first.name).symlink_to(study.runs / first.name, target_is_directory=True)
    retry = stage.inventory(retry_workspace, study.assignments, study.candidate, study.spec, 2)

    assert original["coverage"]["failed"] == [second.name]
    assert retry["cases"][0] == original["cases"][0]
    assert stage.next_case(retry, None) == second.name
    assert inventory(study) == original


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


def test_only_the_frozen_conditional_receipt_can_allow_science_changes(study):
    first = study.assignments[0]
    offsets = dict(c0=1, fitted_c=1)
    seal_pair(study, first, fixes=dict.fromkeys(("baseline", "candidate"), offsets))
    result = inventory(study)
    assert result["comparison"] == "exact"
    assert result["coverage"]["invalid"] == [first.name]
    with pytest.raises(ValueError, match="Only the frozen"):
        stage.comparison_mode(dict(study.spec, schedule="conditional-residual"))


def test_combined_receiver_solver_pin_is_specific_to_the_entire_spec(study, monkeypatch):
    spec = dict(study.spec, schedule="conditional-residual", solver="collapsed-repair")
    monkeypatch.setattr(stage, "Q15_COLLAPSED_REPAIR", canonical_digest(spec))
    assert stage.comparison_mode(spec) == "conditional-residual"
    with pytest.raises(ValueError, match="Only the frozen"):
        stage.comparison_mode(dict(spec, regional_veto=False))


def test_approximate_stage_scores_changed_evidence_and_negative_results(conditional_study, monkeypatch):
    study = conditional_study
    first, second, third, fourth = study.assignments
    lat, lon = REGION["center"]
    monkeypatch.setattr(stage, "pinned", lambda *args: dict(cases=[
        dict(dataset_label=a.name, authority_eligible=True, reference=dict(latitude_deg=lat, longitude_deg=lon))
        for a in study.assignments]))

    seal_pair(study, first, (4., 3.), fixes=dict(baseline=dict(c0=1, fitted_c=1),
                                               candidate=dict(c0=3, fitted_c=1)))
    lead = inventory(study)
    change = lead["cases"][0]["audit"]
    assert lead["coverage"]["verified"] == [first.name]
    assert change["selected"] == dict(selected_common=1, selected_lost=1, selected_added=0)
    assert change["figures_changed"] == ["position"]
    assert change["owners_equal"] == dict(c0=False, fitted_c=True)
    assert change["scientific_evidence_equal"] == dict(grid=False, path=False)
    assert stage.next_case(lead, None) == second.name
    assert stage.score(lead)["quality"] is None

    seal_pair(study, second, (4., 3.), fixes=dict(baseline=dict(c0=1, fitted_c=1)))
    reached = inventory(study)
    assert reached["cases"][1]["audit"]["figures_lost"] == sorted(PLOTS)
    assert stage.next_case(reached, None) == third.name
    seal_pair(study, third, (4., 3.), fixes=dict(candidate=dict(c0=2, fitted_c=1)))
    seal_pair(study, fourth, (4., 3.))

    result = stage.score(inventory(study))
    assert result["coverage"]["verified"] == [a.name for a in study.assignments]
    assert not result["elapsed_gates"]["passed"]
    assert not result["quality"]["preserved"] and not result["geographic_confirmation"]
    site, = result["quality"]["by_site"]
    assert site["median_elapsed_ratio"] == site["summed_elapsed_ratio"] == .75
    for arm in ARMS:
        scored = site["arms"][arm]
        assert scored["matched_fixes"] == [first.name]
        assert scored["lost_containing_fixes"] == [second.name]
        assert scored["added_fixes"] == [third.name]
        assert scored["both_withheld"] == [fourth.name]
        assert scored["no_worse"] == dict.fromkeys(("p50", "p90"), arm == "fitted_c")
        assert not scored["preserved"]


@pytest.mark.parametrize("kind", ["terminal", "figure", "grid", "session", "native"])
def test_approximate_receipts_still_reject_unbound_evidence(conditional_study, kind):
    study = conditional_study
    first = study.assignments[0]
    path = seal_pair(study, first, fixes=dict(candidate=dict(c0=1, fitted_c=1)))
    root = path.parent / "candidate"
    run = stage.read(path)["runs"]["candidate"]["receipt"]["run_id"]
    manifest = pair.FastStandardAnalysisStore(root).folder(run) / "manifest.json"
    if kind == "session":
        manifest.write_text(json.dumps(dict(stage.read(manifest), session_id="another session")))
    else:
        targets = {"terminal": pair.FastScanStore(root).automatic_workspace(run) / "terminal.json",
                   "figure": next(manifest.parent.glob("*.png")),
                   "grid": manifest.parent / "position-grid.json",
                   "native": pair.FastScanStore(root).automatic_workspace("detector") / "detections.json"}
        targets[kind].write_text("{}")
    result = inventory(study)
    assert result["coverage"]["invalid"] == [first.name]
    assert stage.score(result)["quality"] is None
