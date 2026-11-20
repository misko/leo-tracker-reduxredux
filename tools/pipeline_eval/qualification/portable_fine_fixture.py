"""Freeze unmodified producer fine scores from checksum-bound paired CI16 windows."""

import argparse
from hashlib import sha256
from pathlib import Path
from struct import Struct
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import prepared_hotpath, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import fine_search_trial as prior
from . import original_kernel_trial as original
from . import prepared_hotpath_trial as prepared
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/retry-and-transfer/portable-fine"
PARENT = "905317d53cb7b41a341bc6c121bc99bddf9caf4da1e666f1e3580111184c4895"
HEADER = Struct("<8sI")
VISIT = Struct("<2I")
CALL = Struct("<3I2d")


def parent_lock():
    seal = whole_iq.read(whole_iq.checked(prior.REPORT / "qualification-lock.json", PARENT))
    path = whole_iq.checked(prior.REPORT / "input-lock.json", seal["files"]["input-lock.json"])
    return whole_iq.read(path)


def archive_lane(values, samples):
    for lane in range(2):
        if np.array_equal(values.real, samples[:, lane, 0]) and np.array_equal(
            values.imag, samples[:, lane, 1]
        ):
            return lane
    raise ValueError("original fine score did not receive a captured physical antenna")


def record_window(acquisition, window, template, policy):
    fft, peak = acquisition._normalized_frame_scores_fft, acquisition._quadratic_peak
    calls, inputs = [], []
    pending = None

    def save_scores(values, reference, rate, epoch, frequencies, symbols, *, transform_size):
        nonlocal pending
        if (
            pending is not None
            or values.shape != (200_000,)
            or values.dtype != np.complex128
            or not np.array_equal(reference, template)
            or rate != 10_000_000
            or symbols != prepared_hotpath.SYMBOLS
            or transform_size != 20_000
            or not 2 <= len(frequencies) <= 321
        ):
            raise ValueError("the captured scorer departed from its qualified 10 MHz geometry")
        lane = next((lane for old, lane in inputs if old is values), None)
        if lane is None:
            lane = archive_lane(values, window.samples)
            inputs.append((values, lane))
        before = process_time_ns()
        scores = fft(
            values, reference, rate, epoch, frequencies, symbols, transform_size=transform_size
        )
        elapsed = process_time_ns() - before
        pending = (
            scores,
            dict(lane=lane, epoch=int(epoch), absolute=frequencies[0], fft_cpu_ns=elapsed),
        )
        return scores

    def save_peak(grid, scores, winner):
        nonlocal pending
        result = peak(grid, scores, winner)
        if pending is None:
            return result
        values, meta = pending
        if scores is not values or any(
            right - left != 500.0 for left, right in zip(grid[:-1], grid[1:], strict=True)
        ):
            raise ValueError("the residual CFO grid differs from the captured fine FFT plan")
        order = sorted(
            range(len(grid)), key=lambda i: (scores[i], -abs(grid[i]), -grid[i]), reverse=True
        )
        if order[0] != winner:
            raise ValueError("the installed candidate selector changed its exact tie rule")
        vector = np.asarray(scores, dtype="<f8")
        calls.append(
            (
                dict(
                    meta,
                    bins=len(grid),
                    residual=grid[0],
                    scores_sha256=sha256(vector).hexdigest(),
                    winner=winner,
                    runner=order[1],
                    gap=scores[winner] - scores[order[1]],
                    interpolated=result,
                ),
                vector,
            )
        )
        pending = None
        return result

    with (
        patch.object(acquisition, "_normalized_frame_scores_fft", save_scores),
        patch.object(acquisition, "_quadratic_peak", save_peak),
    ):
        packet, _ = prepared.sample(window, policy)
    if pending is not None or {row["lane"] for row, _ in calls} != {0, 1}:
        raise ValueError(
            "reference fixture must sample the supported scoring path on both antennas"
        )
    return packet, calls


def freeze(folder, ident):
    from leo.analysis.starlink import acquisition

    lock = parent_lock()
    cfg = lock["cases"][ident]
    if not Path(acquisition.__file__).is_relative_to(cfg["root"]):
        raise ValueError("freeze must run in the locked capture producer")
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        whole_iq.checked(Path(path), digest)
    case = _load_case(ident)
    _, policy, source = exact.lineage.source_lineage(case)
    if source["capture"]["input_manifest_sha256"] != cfg["input_manifest"]:
        raise ValueError("capture manifest changed from the prior signed panel")
    libs = {
        name: whole_iq.checked(Path(info["path"]), info["sha256"])
        for name, info in lock["libs"].items()
        if name != "fine"
    }
    template = np.asarray(acquisition.qin_edge_pilot_frame(10_000_000, cfg["edge"]), dtype="<c16")
    grid = PersistentGrid(libs["prepared"])
    folder.mkdir(parents=True)
    bundle, scores_path = folder / "captured.iq", folder / "pocketfft-scores.bin"
    locks = []
    try:
        with (
            bundle.open("xb") as binary,
            scores_path.open("xb") as reference,
            exact.refiners(libs),
            grid.route(acquisition, exact.starts.screen_module()),
            patch.object(
                acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
            ),
        ):
            binary.write(HEADER.pack(b"LEOFINE1", len(cfg["rows"])))
            template.tofile(binary)
            for wanted in cfg["rows"]:
                visit = wanted["visit"]
                segment, digest, window = original.decode(case, visit)
                raw = np.ascontiguousarray(window.samples, dtype="<i2")
                if (segment, digest, window.iq_sha256) != (
                    wanted["segment"],
                    wanted["manifest"],
                    wanted["iq_sha256"],
                ) or "sha256:" + sha256(raw).hexdigest() != window.iq_sha256:
                    raise ValueError("signed segment or captured CI16 bytes changed")
                packet, calls = record_window(acquisition, window, template, policy)
                if packet[1] != wanted["probes"]:
                    raise ValueError("reference observer changed the archived native detector")
                binary.write(VISIT.pack(visit, len(calls)))
                raw.tofile(binary)
                rows = []
                for row, values in calls:
                    binary.write(
                        CALL.pack(
                            *(row[k] for k in ("lane", "epoch", "bins", "absolute", "residual"))
                        )
                    )
                    values.tofile(reference)
                    rows.append(row)
                locks.append(
                    dict(
                        visit=visit,
                        kind=wanted["kind"],
                        segment=segment,
                        raw_sha256=window.iq_sha256,
                        manifest=digest,
                        rows=rows,
                    )
                )
                print(ident, visit, len(calls), flush=True)
    finally:
        grid.clear_cache()
    save_json(
        folder / "reference-lock.json",
        dict(
            case=ident,
            edge=cfg["edge"],
            parent_sha256=PARENT,
            capture_manifest=cfg["input_manifest"],
            template_sha256=sha256(template).hexdigest(),
            producer=str(acquisition.__file__),
            producer_sha256=_sha(Path(acquisition.__file__)),
            files={path.name: _sha(path) for path in (bundle, scores_path)},
            visits=locks,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=local_output)
    parser.add_argument("case", choices=parent_lock()["cases"])
    args = parser.parse_args()
    freeze(args.folder, args.case)
