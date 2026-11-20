import json
from copy import deepcopy
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import clock_chain_controls as controls
from tools.pipeline_eval.qualification import clock_chain_raw as raw_replay
from tools.pipeline_eval.qualification import clock_chain_trial as chain


def test_complete_product_binds_factor_bytes_and_rejects_dropped_lane(tmp_path):
    factor = tmp_path / "native.json"
    factor.write_bytes(b"native detector bytes")
    raw = dict(
        id="DS26-0036",
        raw_gate="fresh whole-recording native GLRT",
        native_sha256=sha256(factor.read_bytes()).hexdigest(),
        detector_sha256="detector",
        native_input_manifest_sha256="capture",
        analysis_manifest_sha256="analysis",
        iq_bytes=300,
        recording_windows=3,
        processed_windows=2,
        invalid_capture=1,
        probe_rows=4,
        candidate_rows=7,
        positive_candidates=2,
    )
    case = {"id": raw["id"], "recording": {"window_count": 3}}
    ordinary = {"raw": raw}
    fresh = {
        "raw": dict(raw),
        "raw_lanes": [
            {"decoded_visits": 1, "decoded_bytes": 100},
            {"decoded_visits": 2, "decoded_bytes": 200},
        ],
    }
    chain.verify_product(case, ordinary, fresh, factor)
    incomplete = deepcopy(fresh)
    incomplete["raw_lanes"].pop()
    with pytest.raises(ValueError, match="capture coverage"):
        chain.verify_product(case, ordinary, incomplete, factor)
    factor.write_bytes(b"altered detector bytes")
    with pytest.raises(ValueError, match="factor bytes"):
        chain.verify_product(case, ordinary, fresh, factor)


def test_compact_reference_requires_same_factors_catalogue_and_original_tile(monkeypatch):
    capture = dict(
        id="DS26-0036", native_sha256="factors", catalog_sha256="causal", tile={"id": "0"}
    )
    reference = dict(
        capture,
        method="history_stream_prep",
        detector="ordinary",
        mode="matched-tile",
        result={"status": "ok"},
    )
    monkeypatch.setattr(chain, "_errors", lambda *_: {"c0": 1, "fitted_c": 2})
    assert controls.bind_control(capture, reference)["position_error_km"]["fitted_c"] == 2
    for wrong in (
        dict(reference, native_sha256="capture-era"),
        dict(reference, catalog_sha256="late"),
        dict(reference, tile={"id": "other"}),
    ):
        with pytest.raises(ValueError, match="different ordinary factors or causal authority"):
            controls.bind_control(capture, wrong)


def test_deferred_raw_callbacks_keep_both_captures_and_their_own_start_times(tmp_path, monkeypatch):
    first, second = raw_replay.iq.CASES
    lock = {
        "inputs": {
            first: {"ordinary_native_sha256": "factor-one", "window_count": 5},
            second: {"ordinary_native_sha256": "factor-two", "window_count": 7},
        }
    }
    clocks = iter((100, 110, 130, 160, 170))
    cpu_times = iter((11, 17, 21, 29))
    monkeypatch.setattr(raw_replay, "perf_counter", lambda: next(clocks))
    monkeypatch.setattr(raw_replay, "cpu_s", lambda: next(cpu_times))
    monkeypatch.setattr(raw_replay, "stamp", lambda wall, cpu: dict(start=wall, cpu=cpu))
    monkeypatch.setattr(raw_replay.iq, "read", lambda _: lock)
    monkeypatch.setattr(raw_replay.iq, "source_lock", lambda _: lock)
    monkeypatch.setattr(raw_replay.resources, "cap_address_space", lambda _: None)
    monkeypatch.setattr(raw_replay.resources, "raw_memory", lambda _: {})
    deferred = []

    def record(ident, folder, _cpus, budget, _library, *, finish):
        deferred.append((finish, (folder, ident, budget, "ordinary")))

    def lanes(path):
        lane = int(path.stem[-1])
        visits = (2, 3)[lane] if path.parent.name == first else (3, 4)[lane]
        return dict(decoded_visits=visits, decoded_bytes=20 * visits, largest_read_bytes=20)

    def assemble(_folder, ident, _budget, _detector):
        source = lock["inputs"][ident]
        return dict(
            native_sha256=source["ordinary_native_sha256"], iq_bytes=20 * source["window_count"]
        )

    monkeypatch.setattr(raw_replay.recording_to_v5, "run_recording", record)
    monkeypatch.setattr(raw_replay.raw_stream_trial, "lane_metrics", lanes)
    monkeypatch.setattr(raw_replay.raw_robust, "assemble_raw", assemble)
    raw_replay.run(tmp_path)
    assert len(deferred) == 2
    for finish, args in reversed(deferred):
        finish(*args)

    for ident, begin, cpu in ((first, 110, 11), (second, 130, 17)):
        receipt = json.loads((tmp_path / ident / "raw-stages.json").read_bytes())
        assert receipt["raw_envelope"] == {"start": begin, "cpu": cpu}
        assert receipt["raw"]["native_sha256"] == lock["inputs"][ident]["ordinary_native_sha256"]
    identity = json.loads((tmp_path / raw_replay.RUNNER_RECEIPT).read_bytes())
    assert identity == {"clock_chain_raw.py": sha256(chain.SOURCES[1].read_bytes()).hexdigest()}


def test_new_report_preserves_source_bytes_and_rejects_wrong_raw_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "verify_deployment", lambda: None)
    monkeypatch.setattr(
        chain, "sealed_inputs", lambda _report, sources: dict(source_sha256=sources)
    )
    report = tmp_path / "report"
    chain.lock_report(report)
    digests = chain.archived_sources(report)
    assert json.loads((report / "source-lock.json").read_bytes()) == {"source_sha256": digests}
    for source in chain.SOURCES:
        assert (report / "source" / f"{source.name}.txt").read_bytes() == source.read_bytes()
    with pytest.raises(FileExistsError):
        chain.lock_report(report)

    raw = tmp_path / raw_replay.RUNNER_RECEIPT
    raw.write_text(json.dumps({"clock_chain_raw.py": "older source"}))
    with pytest.raises(ValueError, match="locked raw runner"):
        chain.require_current_lock(report, tmp_path)
    raw.write_text(json.dumps({"clock_chain_raw.py": digests["clock_chain_raw.py"]}))
    chain.require_current_lock(report, tmp_path)


def test_published_runner_snapshots_match_the_historical_source_lock():
    sources = json.loads((chain.REPORT / "source-lock.json").read_bytes())["source_sha256"]
    assert chain.archived_sources(chain.REPORT) == {
        source.name: sources[source.name] for source in chain.SOURCES
    }
