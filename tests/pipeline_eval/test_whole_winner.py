import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import whole_winner_handoff as handoff
from tools.pipeline_eval.qualification import whole_winner_results as results
from tools.pipeline_eval.variants import winner_stream


def recording(tmp_path, monkeypatch):
    library = "b" * 64
    manifests = ["a" * 64, "c" * 64]
    case = dict(
        session_id="captured",
        recording=dict(
            window_count=2,
            segments=[
                dict(path=f"captures/segment-{i}/manifest.json", sha256=digest)
                for i, digest in enumerate(manifests)
            ],
        ),
    )
    authority = [
        dict(
            scope=f"segment-{i:08d}",
            path=f"/srv/bulk/captures/segment-{i}",
            manifest_digest="sha256:" + token,
            windows=1,
        )
        for i, token in enumerate(manifests)
    ]
    manifest = handoff.capture_release.inventory_digest(authority, 2)
    capture = {"input_manifest_sha256": manifest}
    monkeypatch.setattr(
        handoff.capture_release,
        "producer",
        lambda *_: SimpleNamespace(input_manifest_sha256=manifest, root=Path("/decoder")),
    )
    clock = dict(monotonic_ns=600, realtime_ns=900)
    anchor = dict(before=clock, after=clock, sample_counter=100)
    candidate = dict(
        candidate_rank=0,
        fractional_epoch_offset_samples=0.2,
        fractional_margin=0.4,
        fractional_tracking_cfo_hz=10.2,
        integer_epoch_sample=100,
        passed_fractional_margin_gate=True,
    )
    probes = [
        dict(
            receiver_id=i,
            channel=1,
            actual_rf_hz=11e9,
            valid_start_counter=100,
            visit_index=0,
            probe_index=i,
            candidates=[candidate] if i == 0 else [],
        )
        for i in range(2)
    ]
    lanes = []
    for i, token in enumerate(manifests):
        visit = dict(
            kind="visit",
            visit=i,
            segment=i,
            sequence=0,
            generation=1,
            sample_start=100 + i * 200_000,
            sample_end=100 + (i + 1) * 200_000,
            input_bytes=1_600_000,
            iq_sha256=f"sha256:{i:064x}",
            rf_mapping_authority="hypothesis",
            clock_anchor=anchor if i == 0 else None,
            status="processed" if i == 0 else "invalid_capture",
            probes=probes if i == 0 else [],
            delivery_clock=clock,
            reason="test fixture",
        )
        segment = dict(
            kind="segment",
            segment=i,
            count=1,
            manifest_digest="sha256:" + token,
            path=authority[i]["path"],
            library_sha256="sha256:" + library,
            radio_id="same-radio",
            detector_cpu_s=5.0,
            detector="ordinary",
        )
        lane = [visit, segment, dict(kind="worker", worker=i)]
        (tmp_path / f"replayed-{i}.jsonl").write_bytes(
            b"".join(handoff.encoded(item) + b"\n" for item in lane)
        )
        lanes.append(lane)
    return case, capture, library, lanes


def test_private_handoff_reproduces_entire_original_native_commitment(tmp_path, monkeypatch):
    case, capture, library, lanes = recording(tmp_path, monkeypatch)
    stock, counts = handoff.recording.native_document(case, lanes, capture)
    binary = handoff.encoded(stock) + b"\n"
    public = hashlib.sha256(binary).hexdigest()
    expected = io.BytesIO()
    private, size = winner_stream.convert(io.BytesIO(binary), expected, public)
    actual = io.BytesIO()
    receipt = handoff.assemble(tmp_path, case, capture, library, actual)
    assert receipt["native_sha256"] == "sha256:" + public
    assert receipt["private_sha256"] == private
    assert receipt["handoff_bytes"] == size
    assert receipt["counts"] == counts
    assert receipt["decoder_root"] == "/decoder"
    assert actual.getvalue() == expected.getvalue()
    assert not (tmp_path / "native.json").exists()


def test_private_handoff_rejects_changed_segment_and_second_pass(tmp_path, monkeypatch):
    case, capture, library, _ = recording(tmp_path, monkeypatch)
    native = tmp_path / "replayed-1.jsonl"
    original = native.read_bytes()
    native.write_bytes(original.replace(b'"count":1', b'"count":2'))
    with pytest.raises(ValueError, match="incomplete or duplicated detector segment"):
        handoff.assemble(tmp_path, case, capture, library, io.BytesIO())
    native.write_bytes(original)
    digest = handoff.virtual_native

    def change_after_first_pass(*args):
        native.write_bytes(original.replace(b"test fixture", b"other record"))
        return digest(*args)

    monkeypatch.setattr(handoff, "virtual_native", change_after_first_pass)
    with pytest.raises(ValueError, match="messages changed"):
        handoff.assemble(tmp_path, case, capture, library, io.BytesIO())


def test_published_whole_iq_scores_reproduce_without_raw_recordings(tmp_path):
    source = results.trial.REPORT
    comparison = results.score(source, tmp_path)
    assert set(comparison) == {"DS26-0122", "DS29-0082"}
    assert all(
        row == dict(paired=True, exact=True, identical_handoff_projection=True)
        for row in comparison.values()
    )
    for name in ("scores.csv", "resources.csv", "parity.json"):
        assert (tmp_path / name).read_bytes() == (source / name).read_bytes()
