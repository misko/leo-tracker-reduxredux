"""Export one authentic capture-era native coarse call for an offline architecture test."""

import argparse
import json
import platform
from pathlib import Path
from statistics import median
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from .full_v5_check import BULK, PRODUCERS, _bind_producer, _load_case, _sha


def export(out):
    from leo.analysis.starlink import _native_acquisition, acquisition
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    from ..variants.iq_stream import load_windows

    ident, segment, sequence = "DS26-0036", 0, 1
    case = _load_case(ident)
    policy = FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[ident], policy)
    locator = case["recording"]["segments"][segment]
    (window,) = load_windows(
        dict(
            recording_path=str(BULK / locator["path"]),
            recording_sha256="sha256:" + locator["sha256"],
        ),
        (sequence,),
    )
    native = _native_acquisition.folded_anchor_score_grid
    captured = []

    def trace(*args):
        scores = native(*args)
        if not captured:
            captured.append((args, scores))
        return scores

    with patch.object(_native_acquisition, "folded_anchor_score_grid", trace):
        result = analyze_window(window, window.receiver_ids, None, policy)
    if result.status != "processed" or not captured:
        raise ValueError("the frozen visit did not call the deployed native folded grid")
    out.mkdir(parents=True, exist_ok=False)
    args, scores = captured[0]
    names = ("samples", "template", "frequencies", "starts", "stops", "frame_offsets", "prefix")
    dtypes = ("<c16", "<c16", "<f8", "<i8", "<i8", "<i8", "<f8")
    arrays = {}
    for name, value, dtype in zip(
        (*names, "scores"), (*args[:7], scores), (*dtypes, "<f8"), strict=True
    ):
        values = np.ascontiguousarray(value, dtype=dtype)
        path = out / f"{name}.bin"
        values.tofile(path)
        arrays[name] = dict(
            path=path.name, dtype=dtype, shape=list(values.shape), sha256=_sha(path)
        )
    root = Path(acquisition.__file__).parent
    sources = (
        Path(acquisition.__file__),
        Path(_native_acquisition.__file__),
        root / "_native_acquisition.c",
        root / "_native_acquisition_grid.inc",
    )
    manifest = dict(
        recording=ident,
        segment=segment,
        sequence=sequence,
        visit=window.acquisition["global_visit"],
        iq_sha256=window.iq_sha256,
        segment_sha256=locator["sha256"],
        receiver=window.receiver_ids[0],
        entry="folded_anchor_score_grid",
        sample_rate_hz=args[7],
        epoch_count=args[8],
        backend=acquisition._folded_anchor_score_grid_backend(),
        arrays=arrays,
        producer=producer,
        source_files={str(p): _sha(p) for p in sources},
        capture_positives=[
            sum((c.fractional_margin or -1) >= 0.025 for c in rx.candidates)
            for rx in result.receivers
        ],
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def benchmark(folder, out):
    from leo.analysis.starlink import _native_acquisition

    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest["source_files"].get(_native_acquisition.__file__) != _sha(
        Path(_native_acquisition.__file__)
    ):
        raise ValueError("coarse fixture must use the actual deployed extension")
    arrays = {}
    for name, spec in manifest["arrays"].items():
        path = folder / spec["path"]
        if _sha(path) != spec["sha256"]:
            raise ValueError("native fixture argument bytes changed")
        arrays[name] = np.fromfile(path, dtype=spec["dtype"]).reshape(spec["shape"])
    names = ("samples", "template", "frequencies", "starts", "stops", "frame_offsets", "prefix")
    args = [arrays[k] for k in names] + [manifest["sample_rate_hz"], manifest["epoch_count"]]
    modes = {
        "deployed_avx2_fma": _native_acquisition.folded_anchor_score_grid,
        "portable_x86": _native_acquisition.folded_anchor_score_grid_portable,
    }
    expected = {key: call(*args) for key, call in modes.items()}
    if expected["deployed_avx2_fma"].tobytes() != arrays["scores"].tobytes():
        raise ValueError("deployed coarse scores differ from the native fixture")
    clocks = {key: [] for key in modes}
    for repeat in range(3):
        for key in modes if repeat % 2 == 0 else reversed(modes):
            wall, cpu = perf_counter_ns(), process_time_ns()
            scores = modes[key](*args)
            clocks[key].append(
                dict(
                    wall_ms=(perf_counter_ns() - wall) / 1e6, cpu_ms=(process_time_ns() - cpu) / 1e6
                )
            )
            if scores.tobytes() != expected[key].tobytes():
                raise ValueError("coarse backend was unstable on the frozen input")
    portable = folder / "portable-x86-scores.bin"
    expected["portable_x86"].astype("<f8", copy=False).tofile(portable)
    result = dict(
        architecture=platform.machine(),
        fixture_manifest_sha256=_sha(manifest_path),
        boundary="one folded coarse grid, one RX, no window decoding or later scoring",
        portable_score_sha256=_sha(portable),
        clocks=clocks,
        median_cpu_ms={k: median(r["cpu_ms"] for r in v) for k, v in clocks.items()},
        portable_vs_deployed_max_abs=float(
            np.max(np.abs(expected["portable_x86"] - arrays["scores"]))
        ),
        portable_same_best_epoch=int(np.argmax(expected["portable_x86"]))
        == int(np.argmax(arrays["scores"])),
    )
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--time-fixture", type=Path)
    args = parser.parse_args()
    if args.time_fixture is None:
        export(args.out)
    else:
        benchmark(args.time_fixture, args.out)
