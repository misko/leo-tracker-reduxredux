import copy
import importlib.util
import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest

spec = importlib.util.spec_from_file_location(
    "support136_test", Path(__file__).with_name("adapter.py")
)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def fixture():
    counter = 2**60 + 123
    origin, fs = 1_000_000_000_000, 10_000
    timing = NS(
        session_id="session",
        sample_rate_hz=fs,
        first_sample_estimate_utc_ns=origin,
        session_start_device_sample_counter=counter,
    )
    source = NS(
        session_id="session",
        sample_rate_hz=fs,
        timing=timing,
        qualified=True,
        input_manifest_sha256="capture",
        analysis_manifest_sha256="analysis",
        raw_recording_authority_digest="raw",
        stream_generation="generation",
        radio_id="radio",
    )
    points, probes = [], []
    for index in range(2):
        group = canonical_digest(dict(capture="capture", visit=0, rx=0, probe=index))
        cid = canonical_digest(dict(group=group, rank=0, analysis="analysis"))
        relative = 1000 + 200 * index

        def utc(local, relative=relative):
            return origin + round((relative + local) * 1e9 / fs)

        probe = NS(
            visit_index=0,
            receiver_id=0,
            probe_index=index,
            payload_start_sample=500,
            valid_start_counter=counter + 1000,
            actual_rf_hz=11e9,
            edge="lower",
            channel=1,
        )
        point = NS(
            candidate_id=cid,
            candidate_rank=0,
            source_group_id=group,
            session_id="session",
            input_manifest_digest="capture",
            raw_recording_authority_digest="raw",
            stream_generation="generation",
            radio_id="radio",
            visit_index=0,
            receiver_id=0,
            probe_index=index,
            actual_rf_hz=11e9,
            edge="lower",
            channel=1,
            source_sample_start=500 + 200 * index + 5,
            source_sample_end=500 + 200 * index + 15,
            support_start_utc_ns=utc(5),
            support_center_utc_ns=utc(10),
            support_end_utc_ns=utc(15),
            measured_cfo_hz=100.0 + index,
            margin=3.0 + index,
        )
        probes.append(probe)
        points.append(point)
    source.probes = tuple(probes)
    obs = NS(
        window_ids=tuple(p.source_group_id for p in points),
        times_s=np.array([(p.support_center_utc_ns - origin) / 1e9 for p in points]),
        measured_hz=np.array([p.measured_cfo_hz for p in points]),
        rf_hz=np.full(2, 11e9),
        receiver=np.array([0, 0]),
        channel=np.array([1, 1]),
        margin=np.array([3.0, 4.0]),
    )
    prepared = NS(
        observations=obs,
        candidate_ids=tuple(p.candidate_id for p in points),
        start_utc_ns=origin,
        bootstrap_tracks=(),
        trajectory_configuration_sha256="trajectory",
    )
    prepared.evidence_sha256 = canonical_digest(
        dict(
            capture="capture",
            analysis="analysis",
            refinement="off",
            selection="highest-original-margin-rank-id-v1",
            candidate_ids=prepared.candidate_ids,
            window_ids=obs.window_ids,
            bootstrap_tracks=(),
            trajectory_configuration="trajectory",
            **{name: getattr(obs, name).tolist() for name in adapter.OBSERVATION_FIELDS},
        )
    )
    binding = dict(
        session_id="session",
        input_manifest_sha256="capture",
        analysis_manifest_sha256="analysis",
        observation_order_signature=adapter.observation_signature(obs),
    )
    return source, prepared, points, binding


def test_exact_public_join_preserves_large_counter_precision_and_same_visit_windows():
    source, prepared, points, binding = fixture()
    result = adapter.adapt_support(source, prepared, list(reversed(points)), binding)
    assert result["available"] == 2 and result["observations"] == 2
    assert [r["candidate_id"] for r in result["rows"]] == list(prepared.candidate_ids)
    first, second = result["rows"]
    assert first["device_sample_start"] == 2**60 + 123 + 1005
    assert second["device_sample_start"] - first["device_sample_start"] == 200
    assert first["acquisition_id"] != second["acquisition_id"]
    assert first["visit_index"] == second["visit_index"] == 0
    assert first["support_start_ns"] == points[0].support_start_utc_ns
    assert first["actual_rf_hz"] == 11e9 and first["edge"] == "lower"


def test_missing_projection_or_probe_retains_every_original_row():
    source, prepared, points, binding = fixture()
    result = adapter.adapt_support(source, prepared, points[:1], binding)
    assert result["observations"] == 2 and result["available"] == 1
    assert result["rows"][1]["window_id"] == prepared.observations.window_ids[1]
    assert result["rows"][1]["support_reason"] == "selected-candidate-not-projected"
    source.probes = source.probes[:1]
    result = adapter.adapt_support(source, prepared, points, binding)
    assert result["rows"][1]["support_reason"] == "public-probe-authority-missing"


def test_changed_original_fields_order_or_evidence_are_not_accepted():
    source, prepared, points, binding = fixture()
    changed = copy.deepcopy(points)
    changed[0].measured_cfo_hz += 1
    with pytest.raises(ValueError, match="observation field"):
        adapter.adapt_support(source, prepared, changed, binding)
    prepared.observations.times_s = prepared.observations.times_s[::-1]
    with pytest.raises(ValueError, match="signature"):
        adapter.adapt_support(source, prepared, points, binding)
    source, prepared, points, binding = fixture()
    prepared.evidence_sha256 = "changed"
    with pytest.raises(ValueError, match="window evidence"):
        adapter.adapt_support(source, prepared, points, binding)


def test_wrong_local_offset_conversion_or_rf_edge_admission_rejected():
    source, prepared, points, binding = fixture()
    points[0].source_sample_start += 1
    with pytest.raises(ValueError, match="sample/UTC"):
        adapter.adapt_support(source, prepared, points, binding)
    source, prepared, points, binding = fixture()
    source.probes[0].edge = "upper"
    with pytest.raises(ValueError, match="RF/edge"):
        adapter.adapt_support(source, prepared, points, binding)


def test_reference_fields_are_never_accessed():
    source, prepared, points, binding = fixture()

    class Poison:
        def __getitem__(self, key):
            raise AssertionError("Reference access forbidden")

    source.reference = Poison()
    prepared.reference = Poison()
    binding["reference"] = Poison()
    result = adapter.adapt_support(source, prepared, points, binding)
    assert result["available"] == 2


def test_missing_support_adapter_to_pairing_keeps_every_row_without_invented_edge():
    pairing = runpy.run_path(str(Path(__file__).with_name("pair_score.py")))
    source, prepared, points, binding = fixture()
    support = adapter.adapt_support(source, prepared, points[:1], binding)
    result = pairing["pair_rows"](support["rows"])
    assert support["rows"][1]["edge"] is None
    assert result["observations"] == 2 and len(result["unpaired"]) == 2
    assert result["reason_counts"]["missing-support"] == 1
    source.probes = source.probes[:1]
    support = adapter.adapt_support(source, prepared, points, binding)
    result = pairing["pair_rows"](support["rows"])
    assert result["observations"] == 2 and len(result["unpaired"]) == 2
    assert support["rows"][1]["edge"] == "lower"
    assert support["rows"][1]["acquisition_id"] is None
