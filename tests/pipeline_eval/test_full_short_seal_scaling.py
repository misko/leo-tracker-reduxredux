from hashlib import sha256
from pathlib import Path

import pytest


@pytest.fixture
def scaling(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    from reports.ALGO08.v3 import full_short_seal_scaling

    return full_short_seal_scaling


def test_real_seal_rechecks_original_bytes_and_binding(scaling, tmp_path):
    from leo.contracts.digests import canonical_digest, canonical_json_bytes

    raw, detector = "sha256:" + "d"*64, "1"*64
    probes = [{"candidates": []}, {"candidates": []}]
    binding = canonical_digest(["cancellation", raw, detector, probes])
    document = dict(source=dict(probes=probes, session_id="s", input_manifest_sha256="inventory",
                                raw_recording_authority_digest=raw, analysis_manifest_sha256=binding),
                    provenance=dict(detector_sha256="sha256:" + detector, window_count=1, processed_windows=1),
                    delivery_clocks=[{}])
    digest = sha256(canonical_json_bytes(document)).hexdigest()
    saved = tmp_path / "detections.json"
    result = scaling.measure(document, digest, saved)
    assert saved.read_bytes() == canonical_json_bytes(document)
    assert result["sha256"] == digest
    assert {"canonical_json", "file_fsync", "directory_fsync", "readback", "source_verification"} <= result["stages"].keys()
    with pytest.raises(ValueError, match="durable readback"):
        scaling.measure(document, "0"*64, tmp_path / "wrong.json")


def test_charges_full_tail_once_preserving_uninstrumented_failure(scaling):
    rows = [dict(stages=(5., 3., 2.), compressed_MB=4.), dict(stages=(0., 0., 5.), compressed_MB=8.)]
    result = scaling.transfer(rows, 1., 2., .5, {"optimistic": .5, "stressed": 1.}, .5)
    assert result["old_through_seal_scaled_per_MB"] == pytest.approx((.875, 12.5/15))
    assert result["optimistic"]["once_sealed"] == pytest.approx((.8, 11/15))
    assert result["stressed"]["once_sealed_with_worker"] == pytest.approx((.85, 12/15))


def test_combines_full_document_cpu_with_observed_wait_once(scaling):
    rows = [{"arm": "full", "stages": {"complete": {"cpu_ns": 40_000_000, "wall_ns": 70_000_000}}},
            {"arm": "full", "stages": {"complete": {"cpu_ns": 50_000_000, "wall_ns": 65_000_000}}}]
    prefix = [dict(wall_ns=1_000_000_000, cpu_ns=300_000_000, acquire_wall_ns=700_000_000, acquire_cpu_ns=280_000_000)]
    assert scaling.shared_tails(rows, prefix) == pytest.approx(
        {"optimistic": .065, "stressed": .330, "maximum_observed_non_cpu_seal_s": .280})
