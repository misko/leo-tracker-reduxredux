import pytest

from tools.pipeline_eval.qualification import recording_to_v5 as full
from tools.pipeline_eval.qualification.full_v5_check import (
    ALIAS_HZ,
    BULK,
    Producer,
    compare_probes,
    factor_candidate,
)


def fractional(rank, epoch, cfo, margin):
    return factor_candidate(
        rank,
        epoch,
        status="complete",
        offset=0.25,
        cfo=cfo,
        exact=margin + 0.02,
        control=0.02,
        margin=margin,
    )


def test_factor_projection_preserves_fractional_measurement_and_gate():
    assert fractional(3, 1200, -1234.5, 0.025) == {
        "candidate_rank": 3,
        "integer_epoch_sample": 1200,
        "fractional_epoch_offset_samples": 0.25,
        "fractional_tracking_cfo_hz": -1234.5,
        "fractional_exact_score": 0.045,
        "fractional_control_score": 0.02,
        "fractional_margin": 0.025,
        "passed_fractional_margin_gate": True,
    }
    assert fractional(1, 0, 0, 0.0249)["passed_fractional_margin_gate"] is False
    fields = dict(offset=None, cfo=None, exact=None, control=None, margin=None)
    assert factor_candidate(4, 0, status="unbracketed", **fields) is None
    with pytest.raises(ValueError):
        factor_candidate(4, 0, status="complete", **fields)


def test_matches_use_both_aliases_without_reusing_any_positive():
    rate = 10_000_000
    production = {
        "receiver_id": 0,
        "candidates": [
            fractional(0, 13_332, 500, 0.25),
            fractional(1, 1, 1300, 0.25),
            fractional(2, 1000, 1000, 0.05),
            fractional(3, 1234, 1000, 0.02),
        ],
    }
    native = {
        "receiver_id": 0,
        "candidates": [
            fractional(0, 0, ALIAS_HZ + 750, 0.35),
            fractional(1, 13_332, ALIAS_HZ, 0.15),
            fractional(2, 2000, 1000, 0.05),
        ],
    }
    result = compare_probes(production, native, rate)
    assert result["production_complete"] == 4
    assert result["production_positive"] == 3
    assert result["native_positive"] == 3
    assert result["production_only"] == result["native_only"] == 1
    first, second = result["positive_matches"]
    assert (first["production_rank"], first["native_rank"]) == (0, 1)
    assert (second["production_rank"], second["native_rank"]) == (1, 0)
    assert second["epoch_delta_samples"] == -1
    assert second["raw_cfo_delta_hz"] == pytest.approx(ALIAS_HZ - 550)
    assert second["aliased_cfo_delta_hz"] == pytest.approx(-550)


def test_empty_receiver_rows_stay_empty_and_support_cannot_change():
    empty = dict(receiver_id=1, valid_start_counter=900, candidates=[])
    other = dict(empty, candidates=[fractional(0, 1, 0, 0.1)])
    assert compare_probes(empty, other, 10_000_000)["native_only"] == 1
    assert compare_probes(other, empty, 10_000_000)["production_only"] == 1
    with pytest.raises(ValueError):
        compare_probes(empty, dict(other, valid_start_counter=901), 10_000_000)


def test_complete_replay_retains_raw_clock_and_invalid_visit(monkeypatch):
    manifests = [
        dict(path=f"corpus/example/segment{i}/manifest.json", sha256=str(i) * 64) for i in range(2)
    ]
    case = dict(
        id="example",
        session_id="capture-example",
        recording=dict(segments=manifests, window_count=2),
    )
    paths = [str((BULK / row["path"]).parent) for row in manifests]
    inventory_segments = [
        dict(
            scope=f"segment-{i:08d}",
            path=path,
            manifest_digest="sha256:" + manifests[i]["sha256"],
            windows=1,
        )
        for i, path in enumerate(paths)
    ]
    manifest_sha = full.digest(
        dict(
            schema_version=1,
            kind="fast-scan-source",
            recording_name="example",
            segments=inventory_segments,
            window_count=2,
        )
    )
    monkeypatch.setitem(full.PRODUCERS, "example", Producer(BULK, manifest_sha))
    lanes = []
    for i in range(2):
        sample_start = 500 + 210_000 * i
        visit = dict(
            kind="visit",
            segment=i,
            sequence=0,
            visit=i,
            generation=10,
            iq_sha256="sha256:" + str(2 + i) * 64,
            sample_start=sample_start,
            sample_end=sample_start + 200_000,
            input_bytes=1_600_000,
            status="processed" if i == 0 else "invalid_capture",
            clock_anchor={"sample_counter": 500} if i == 0 else None,
            delivery_clock=dict(realtime_ns=i + 1, monotonic_ns=i),
            rf_mapping_authority="hypothesis",
            reason="capture quality",
        )
        visit["probes"] = (
            [
                dict(
                    receiver_id=rx,
                    visit_index=i,
                    valid_start_counter=sample_start,
                    candidates=[fractional(1, 1235, 42, 0.1)] if rx == 0 else [],
                )
                for rx in (0, 1)
            ]
            if i == 0
            else []
        )
        receipt = dict(
            kind="segment",
            segment=i,
            count=1,
            path=paths[i],
            manifest_digest="sha256:" + manifests[i]["sha256"],
            radio_id="radio",
            library_sha256="sha256:" + "4" * 64,
            detector_cpu_s=0.1,
        )
        lanes.append([visit, receipt, dict(kind="worker", worker=i)])
    document, metrics = full.native_document(case, lanes)
    assert document["source"]["session_id"] == "capture-example"
    assert document["source"]["input_manifest_sha256"] == manifest_sha
    assert document["source"]["analysis_manifest_sha256"] != manifest_sha
    assert len(document["source"]["probes"]) == 2
    assert document["source"]["probes"][1]["candidates"] == []
    assert document["clock_anchor"]["sample_counter"] == 500
    assert document["last_sample_counter"] == 410_500
    assert document["provenance"]["excluded_windows"][0]["visit"] == 1
    assert metrics["iq_bytes"] == 3_200_000
    assert metrics["window_delivery_span_s"] == 1e-9
    assert metrics["positive_candidates"] == metrics["empty_probe_rows"] == 1
    with pytest.raises(ValueError, match="terminal receipt"):
        full.native_document(case, [lanes[0], lanes[1][:-1]])
    with pytest.raises(ValueError, match="segment detector"):
        full.native_document(case, lanes, detector="single-rx0")
    for lane in lanes:
        lane[-2]["detector"] = "single-rx0"
    single, _ = full.native_document(case, lanes, detector="single-rx0")
    assert (
        single["source"]["analysis_manifest_sha256"]
        != document["source"]["analysis_manifest_sha256"]
    )
    assert single["provenance"]["detector_mode"] == "single-rx0"


def test_capture_release_uses_raw_manifest_and_original_run_id(tmp_path, monkeypatch):
    import json
    from hashlib import sha256

    from tools.pipeline_eval.qualification import capture_release

    monkeypatch.setattr(capture_release, "BULK", tmp_path)
    path = tmp_path / "example/part/manifest.json"
    path.parent.mkdir(parents=True)
    manifest = dict(
        session_id="part",
        status="complete",
        sample_rate_hz=10_000_000,
        window_ms=20,
        receiver_ids=[0, 1],
        sample_format="ci16_le",
        sample_layout="sample_receiver_iq",
        configuration=dict(targets=[dict(edge="upper")]),
        window_count=2,
    )
    path.write_text(json.dumps(manifest))
    manifest_hash = sha256(path.read_bytes()).hexdigest()
    locator = dict(path="example/part/manifest.json", sha256=manifest_hash)
    inventory = [
        dict(
            scope="segment-00000000",
            path=str(path.parent),
            manifest_digest="sha256:" + manifest_hash,
            windows=2,
        )
    ]
    digest = capture_release.inventory_digest(inventory, 2)
    session = "fast-" + digest[7:39]
    release = next(iter(capture_release.RELEASE_ROOTS))
    case = dict(
        id="example",
        session_id=session,
        run_id="fast-" + full.digest([session, digest, release])[7:39],
        recording=dict(segments=[locator], window_count=2),
    )
    capture = capture_release.read_capture(case)
    assert capture == dict(edge="upper", input_manifest_sha256=digest)
    assert capture_release.producer(case, capture).root == capture_release.RELEASE_ROOTS[release]
    with pytest.raises(ValueError, match="verified installed producer"):
        capture_release.read_capture(dict(case, run_id="another run"))
    path.write_text(json.dumps(dict(manifest, window_count=3)))
    with pytest.raises(ValueError, match="authentication"):
        capture_release.read_capture(case)


def test_request_rebinds_the_new_input_and_retains_original_numerical_settings(tmp_path):
    import json
    from hashlib import sha256

    prior_native_sha = "sha256:" + "0" * 64
    original = tmp_path / "original.json"
    request = dict(
        role="baseline",
        job=dict(
            session="untouched",
            evaluation_reference=None,
            track_config={"config": "same"},
            identity={"session_id": "capture", "input_sha256": prior_native_sha, "run_id": "old"},
            native_input={"path": "/archive/native.json", "sha256": prior_native_sha},
        ),
    )
    raw = full.encoded(request).encode()
    original.write_bytes(raw)
    fresh = tmp_path / "fresh.json"
    fresh.write_text('{"fresh":true}\n')
    rebound = tmp_path / "rebound.json"
    case = dict(
        id="example",
        panel="DS26",
        regions=[],
        session_id="capture",
        request=dict(path=str(original), sha256=sha256(raw).hexdigest()),
        native=dict(sha256=prior_native_sha[7:]),
    )
    public = full.bind_request(case, fresh, rebound)
    job = json.loads(rebound.read_bytes())["job"]
    assert job["track_config"] == request["job"]["track_config"]
    assert job["evaluation_reference"] is None
    assert job["identity"]["session_id"] == "capture"
    assert job["identity"]["run_id"] != "old"
    assert job["native_input"]["path"] == str(fresh)
    assert job["native_input"]["sha256"] == public["native_sha256"]
    assert job["identity"]["input_sha256"] == public["native_sha256"]
