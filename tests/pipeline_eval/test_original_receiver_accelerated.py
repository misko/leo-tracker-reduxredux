from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval import original_receiver as receiver


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], {"peak_selector": "installed", "interior_guard": False}),
        (
            ["--accelerated"],
            {
                "peak_selector": "row-wise",
                "interior_guard": False,
                "fine_backend": "batched",
                "short_fft": True,
            },
        ),
        (
            ["--accelerated", "--peak-selector", "installed", "--fine-search", "pruned"],
            {
                "peak_selector": "installed",
                "interior_guard": False,
                "fine_backend": "pruned",
                "short_fft": True,
            },
        ),
    ],
)
def test_accelerated_command_selects_only_the_requested_kernels(
    tmp_path, monkeypatch, flags, expected
):
    out = tmp_path / "run"
    monkeypatch.setattr(receiver, "input_case", lambda *_: {"id": "input"})

    def prepare(*args, **options):
        assert options == expected
        out.mkdir()
        return {}

    monkeypatch.setattr(receiver, "prepare", prepare)
    monkeypatch.setattr(
        receiver, "run", lambda *_: {"id": "input", "status": "stage_only", "stage": "raw"}
    )
    assert (
        receiver.main(["--case", "input", "--out", str(out), "--cpus", "0", "--smoke", *flags]) == 0
    )


def test_packaged_coarse_kernel_binds_the_measured_qualification():
    library, sha = receiver.SHORT_FFT
    study = library.parents[2]
    result = receiver.whole_iq.read(
        receiver.whole_iq.checked(study / "evidence-lock.json", receiver.SHORT_FFT_QUALIFICATION)
    )
    data = receiver.whole_iq.read(
        receiver.whole_iq.checked(
            study / "qualification.json", result["files"]["qualification.json"]
        )
    )
    assert data["length"] == 256 and data["planner"] == "stored-measure"
    assert data["candidate_sha256"] == receiver._sha(Path(library)) == sha


def test_accelerated_measurement_identity_uses_science_choices_and_ignores_staging_paths():
    initial = {
        "source": {"analysis_manifest_sha256": "initial", "probes": ["same"]},
        "provenance": {"detector_sha256": "previous"},
    }
    lock = {
        "libraries": {"prepared": {"sha256": "binary", "path": "/one"}},
        "peak_selector": {"backend": "row-wise"},
        "coarse_search": {"fft_samples": 256},
    }
    current, copied, changed = (deepcopy(initial) for _ in range(3))
    receiver.bind_short_fft(current, lock)
    lock["libraries"]["prepared"]["path"] = "/two"
    receiver.bind_short_fft(copied, lock)
    assert current == copied
    lock["fine_search"] = {"backend": "batched"}
    receiver.bind_short_fft(changed, lock)
    assert changed["provenance"]["detector_sha256"] != current["provenance"]["detector_sha256"]
    assert (
        changed["source"]["analysis_manifest_sha256"]
        != current["source"]["analysis_manifest_sha256"]
    )
    assert current["source"]["probes"] == changed["source"]["probes"] == ["same"]
