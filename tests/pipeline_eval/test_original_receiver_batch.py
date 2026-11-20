from pathlib import Path

import pytest

from tools.pipeline_eval import original_receiver as receiver


def test_every_enrolled_producer_pin_matches_the_frozen_batch_panel():
    study = receiver.ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/fine-batch"
    authority = receiver.whole_iq.read(
        receiver.whole_iq.checked(study / "qualification-lock.json", receiver.BATCH_QUALIFICATION)
    )
    panel = receiver.whole_iq.read(
        receiver.whole_iq.checked(study / "input-lock.json", authority["files"]["input-lock.json"])
    )
    pinned = {}
    for case in panel["cases"].values():
        root = Path(case["root"])
        pinned[root] = case["sources"][str(root / "leo/analysis/starlink/acquisition.py")]
    assert pinned == receiver.ROW_SELECTOR_PRODUCERS


def test_normal_cli_selects_batched_fine_without_a_candidate_stop(tmp_path, monkeypatch):
    out = tmp_path / "result"
    monkeypatch.setattr(receiver, "input_case", lambda *_: {"id": "fixture"})

    def prepare(*args, **options):
        assert options == dict(
            peak_selector="row-wise", interior_guard=False, fine_backend="batched"
        )
        out.mkdir()
        return options

    monkeypatch.setattr(receiver, "prepare", prepare)
    monkeypatch.setattr(
        receiver, "run", lambda *_: dict(id="fixture", status="stage_only", stage="raw")
    )
    assert (
        receiver.main(
            [
                "--case",
                "fixture",
                "--out",
                str(out),
                "--cpus",
                "22",
                "--smoke",
                "--peak-selector",
                "row-wise",
                "--fine-search",
                "batched",
            ]
        )
        == 0
    )


def test_batched_library_preflight_rejects_missing_avx2_and_wrong_digest(tmp_path, monkeypatch):
    library = tmp_path / "fine_batch.so"
    library.write_bytes(b"qualified fixture")
    monkeypatch.setattr(receiver, "BATCH_LIBRARY_SHA", receiver._sha(library))
    monkeypatch.setattr(receiver.fine_batch, "supports_host", lambda: False)
    with pytest.raises(ValueError, match="requires AVX2"):
        receiver.pruned_library(tmp_path, tmp_path, batched=True)
    monkeypatch.setattr(receiver.fine_batch, "supports_host", lambda: True)
    selected, receipt = receiver.pruned_library(tmp_path, tmp_path, batched=True)
    assert selected == library and receipt["mode"] == "reused" and receipt["command"] is None
    library.write_bytes(b"not the known library")
    with pytest.raises(ValueError, match="declared SHA-256"):
        receiver.pruned_library(tmp_path, tmp_path, batched=True)


def test_batched_worker_checks_runtime_and_staged_abi_before_loading(tmp_path, monkeypatch):
    import numpy
    from numpy.fft import _pocketfft_umath

    from leo.analysis.starlink import acquisition

    source = Path(acquisition.__file__)
    root = source.parents[3]
    monkeypatch.setattr(receiver, "ROW_SELECTOR_PRODUCERS", {root: receiver._sha(source)})
    monkeypatch.setattr(receiver, "FINE_NUMPY_VERSION", numpy.__version__)
    monkeypatch.setattr(
        receiver, "FINE_POCKETFFT_SHA", receiver._sha(Path(_pocketfft_umath.__file__))
    )
    monkeypatch.setattr(receiver.fine_batch, "supports_host", lambda: True)
    library = tmp_path / "fine_batch.so"
    library.write_bytes(b"qualified ABI fixture")
    monkeypatch.setattr(receiver, "BATCH_LIBRARY_SHA", receiver._sha(library))
    evidence = receiver.pruned_fine_evidence(root, batched=True)
    assert (
        evidence["frame_lanes"] == 4
        and evidence["qualification_sha256"] == receiver.BATCH_QUALIFICATION
    )
    sentinel = object()

    def instantiate(binary, owner):
        assert binary == library and owner is acquisition
        return sentinel

    monkeypatch.setattr(receiver.fine_batch, "FineBatch", instantiate)
    lock = dict(producer=str(root), fine_search=evidence)
    assert receiver.fine_search_for(lock, {"fine": library}) is sentinel
    library.write_bytes(b"unverified native ABI")
    with pytest.raises(ValueError, match="declared SHA-256"):
        receiver.fine_search_for(lock, {"fine": library})
