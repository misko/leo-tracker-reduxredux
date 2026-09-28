import hashlib
import json
from types import SimpleNamespace

import numpy as np

from tools.ds7_combined_export import _reuse_hooks, compare_science_outputs


def test_reuse_hooks_are_exact_and_restored(tmp_path) -> None:
    original_store = object()
    original_prepare = object()
    tracking = SimpleNamespace(ScannerTrackingInputStore=original_store)
    preparation = SimpleNamespace(prepare_adaptive_tle_position_inputs=original_prepare)
    raw = object()
    prepared = object()

    with _reuse_hooks(
        tracking,
        preparation,
        session="scan-fw-test",
        bulk_root=tmp_path,
        raw=raw,
        prepared=prepared,
    ) as calls:
        store = tracking.ScannerTrackingInputStore(tmp_path)
        assert store.load("scan-fw-test") is raw
        inputs = SimpleNamespace(load=lambda session: raw)
        assert (
            preparation.prepare_adaptive_tle_position_inputs(
                "scan-fw-test", inputs=inputs, archive=object()
            )
            is prepared
        )
        store.close()

    assert calls == {"store_construct": 1, "load": 1, "prepare": 1, "close": 1}
    assert tracking.ScannerTrackingInputStore is original_store
    assert preparation.prepare_adaptive_tle_position_inputs is original_prepare


def test_comparison_ignores_only_runtime_provenance(tmp_path) -> None:
    reference = tmp_path / "reference"
    combined = tmp_path / "combined"
    reference.mkdir()
    combined.mkdir()
    for root, elapsed in ((reference, 10.0), (combined, 4.0)):
        (root / "tracks.json").write_text(
            f'{{"tracks":[{{"track_id":"x","times_s":[1],"measured_hz":[2],'
            f'"training_mask":[true]}}],"elapsed_seconds":{elapsed}}}'
        )
        banks = root / "banks"
        banks.mkdir()
        (banks / "shortlists.json").write_text('{"shortlists":{"x":[1]}}')
        (banks / "manifest.json").write_text(
            json.dumps(
                {
                    "tracks": [{"track_id": "x"}],
                    "tracks_sha256": "sha256:"
                    + hashlib.sha256((root / "tracks.json").read_bytes()).hexdigest(),
                    "elapsed_seconds": elapsed,
                }
            )
        )
        np.savez(banks / "banks.npz", timing_grid_s=np.asarray([0.0, 0.25]))

    result = compare_science_outputs(
        reference / "tracks.json",
        reference / "banks",
        combined / "tracks.json",
        combined / "banks",
    )

    assert result["array_values_exactly_equal"]
    assert result["tracks_equal_ignoring_elapsed"]


def test_comparison_rejects_manifest_track_mismatch(tmp_path) -> None:
    for name in ("reference", "combined"):
        root = tmp_path / name
        root.mkdir()
        (root / "tracks.json").write_text('{"tracks":[]}')
        banks = root / "banks"
        banks.mkdir()
        (banks / "shortlists.json").write_text('{"shortlists":{}}')
        (banks / "manifest.json").write_text(
            '{"tracks":[],"tracks_sha256":"sha256:not-the-file"}'
        )
        np.savez(banks / "banks.npz", values=np.asarray([1]))

    try:
        compare_science_outputs(
            tmp_path / "reference" / "tracks.json",
            tmp_path / "reference" / "banks",
            tmp_path / "combined" / "tracks.json",
            tmp_path / "combined" / "banks",
        )
    except ValueError as error:
        assert "does not bind" in str(error)
    else:
        raise AssertionError("unbound bank manifest must fail")


def test_reuse_hooks_restore_after_failure(tmp_path) -> None:
    original_store = object()
    original_prepare = object()
    tracking = SimpleNamespace(ScannerTrackingInputStore=original_store)
    preparation = SimpleNamespace(prepare_adaptive_tle_position_inputs=original_prepare)

    try:
        with _reuse_hooks(
            tracking,
            preparation,
            session="scan-fw-test",
            bulk_root=tmp_path,
            raw=object(),
            prepared=object(),
        ):
            raise RuntimeError("expected")
    except RuntimeError:
        pass

    assert tracking.ScannerTrackingInputStore is original_store
    assert preparation.prepare_adaptive_tle_position_inputs is original_prepare
