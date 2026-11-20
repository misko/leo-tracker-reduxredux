"""Pair the installed detector and conservative magnitude preflight on saved IQ."""

import argparse
import gzip
import json
from contextlib import contextmanager, nullcontext
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import capture_bound, iq_stream
from . import capture_detector_lineage, capture_release, capture_starts
from .conditioned_cfo_eval import _test_signal
from .full_v5_check import BULK, _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/capture-bound"
CASES = {"DS26-0036": ((5, (2, 6)), (12, (1, 7))), "DS29-0174": ((8, (2, 6)), (10, (1, 7)))}
MODES = ("stock", "bound")


def freeze(work):
    work.mkdir(parents=True, exist_ok=False)
    library = capture_bound.build(work / "capture-bound.so")
    entries = {}
    for ident, roster in CASES.items():
        case = _load_case(ident)
        capture = capture_release.read_capture(case)
        producer = capture_release.producer(case, capture)
        sources = [
            *[
                producer.root / "leo/scanner" / name
                for name in ("fast_scan_analysis.py", "fast_scan_detector.py")
            ],
            *[
                path
                for pattern in (
                    "acquisition.py",
                    "templates.py",
                    "fast_scan_*.py",
                    "*screen*.py",
                    "_native_acquisition*.so",
                    "_screen_native/*.so",
                    "_sparse_native/*.so",
                )
                for path in (producer.root / "leo/analysis/starlink").glob(pattern)
            ],
        ]
        windows = []
        for segment, sequences in roster:
            source = case["recording"]["segments"][segment]
            try:
                local = iq_stream.load_windows(
                    dict(
                        recording_path=str(BULK / source["path"]),
                        recording_sha256="sha256:" + source["sha256"],
                    ),
                    sequences,
                )
            except iq_stream.IQReadError as error:
                windows.extend(
                    dict(segment=segment, sequence=n, unavailable=str(error)) for n in sequences
                )
                continue
            for w in local:
                visit = w.acquisition["global_visit"]
                file = f"{ident}-{visit}.ci16"
                write(work / file, w.samples.tobytes())
                windows.append(
                    dict(
                        segment=segment,
                        visit=visit,
                        file=file,
                        manifest_sha256=source["sha256"],
                        rows=list(w.samples.shape),
                        meta={
                            k: getattr(w, k)
                            for k in (
                                "sequence",
                                "receiver_ids",
                                "sample_rate_hz",
                                "acquisition",
                                "target_id",
                                "target",
                                "iq_sha256",
                            )
                        },
                    )
                )
        entries[ident] = dict(
            installed_source={str(p): _sha(p) for p in sources},
            windows=windows,
            root=str(producer.root),
            input_manifest_sha256=capture["input_manifest_sha256"],
            edge=capture["edge"],
            archive_sha256=case["native"]["sha256"],
        )
    sources = (
        Path(__file__),
        Path(capture_bound.__file__),
        capture_bound.SOURCE,
        Path(capture_starts.__file__),
        Path(capture_detector_lineage.__file__),
        Path(_test_signal.__code__.co_filename),
        REPORT / "PROTOCOL.md",
        library,
    )
    save_json(
        work / "input-lock.json", dict(cases=entries, sources={str(p): _sha(p) for p in sources})
    )


def verified(work):
    lock = json.loads((work / "input-lock.json").read_bytes())
    if any(_sha(Path(p)) != h for p, h in lock["sources"].items()):
        raise ValueError("runtime source or library differs from its seal")
    return lock


def case_window(work, entry):
    meta = entry["meta"]
    blob = (work / entry["file"]).read_bytes()
    if "sha256:" + sha256(blob).hexdigest() != meta["iq_sha256"]:
        raise ValueError("selected CI16 scratch file differs from archive digest")
    return iq_stream.IQWindow(
        samples=np.frombuffer(blob, dtype="<i2").reshape(entry["rows"]), **meta
    )


def science(row):
    return encoded(
        dict(
            status=row["status"],
            probes=row["probes"],
            attempts=[
                {k: v for k, v in a.items() if k not in ("stage_cpu_ns", "stage_calls")}
                for a in row["attempts"]
            ],
        )
    )


def pair(window, policy, bound, acquisition, screen, order, repetitions):
    rows = []
    for iteration in range(repetitions):
        paired = {}
        for mode in MODES if (iteration + order) % 2 == 0 else MODES[::-1]:
            start = len(bound.rows)
            context = bound.activate(acquisition, screen) if mode == "bound" else nullcontext()
            with context:
                row = capture_starts.trace_capture(window, policy)
            paired[mode] = dict(row, preflight=bound.rows[start:])
        if science(paired["stock"]) != science(paired["bound"]):
            raise ValueError(
                "original and preflight detector disagree on acquired or fractional rows"
            )
        rows.append(paired)
    return rows


def bound_statistics(grid, upper, threshold):
    maximum = grid.max(axis=0)
    eligible = upper < threshold if threshold is not None else np.zeros(upper.shape, dtype=bool)
    return dict(
        cells=grid.size,
        columns=int(upper.size),
        optimistic_cut_columns=int(eligible.sum()),
        optimistic_cut_cells=int(eligible.sum()) * grid.shape[0],
        violations=int((grid > upper[None, :]).sum()),
        max_excess=float(np.max(np.maximum(maximum - upper, 0))),
        bound_min=float(upper.min()),
        bound_median=float(np.median(upper)),
        bound_max=float(upper.max()),
        exact_grid_max=float(maximum.max()),
    )


@contextmanager
def observe(bound, acquisition, screen):
    trace = []
    source = acquisition._folded_anchor_score_grid

    def audit(args, grid, ranking=None):
        record = dict(
            anchors=len(args[4]),
            frequencies=len(args[3]),
            exact_grid=np.asarray(grid),
            ranking=ranking,
        )
        record["upper"] = {
            m: bound.evaluate(acquisition, args, per_tap=m == "per_tap")
            for m in ("blocks", "per_tap")
        }
        trace.append(record)

    def dense(*args):
        grid = source(*args)
        audit(args, grid)
        return grid

    if screen is None:
        with patch.object(acquisition, "_folded_anchor_score_grid", dense):
            yield trace
    else:
        original = screen.acquire

        def screened(module, args, residuals, count, epochsep, cfosep, *, observer=None):
            result = original(module, args, residuals, count, epochsep, cfosep, observer=observer)
            grid = source(*args)
            exact = acquisition._retain_score_map_peaks(
                residuals, grid, count, epochsep, cfosep, args[-1]
            )
            audit(args, grid, capture_starts.peak_rows(exact))
            return result

        with patch.object(screen, "acquire", screened):
            yield trace


def audit_window(window, policy, bound, acquisition, screen):
    with observe(bound, acquisition, screen) as trace:
        result = capture_starts.trace_capture(window, policy)
    out = []
    for line, attempt in zip(trace, result["attempts"], strict=True):
        retained = line["ranking"] if line["ranking"] is not None else attempt["centers"]
        threshold = (
            retained[-1]["score"] if len(retained) == 8 and retained[-1]["score"] > 0 else None
        )
        measures = {}
        for method, measured in line["upper"].items():
            if measured is None:
                measures[method] = dict(status="unsupported")
                continue
            upper, work = measured
            measures[method] = dict(bound_statistics(line["exact_grid"], upper, threshold), **work)
        out.append(
            dict(
                receiver=attempt["receiver"],
                attempt=attempt["attempt"],
                anchors=line["anchors"],
                threshold=threshold,
                retained_exact_equal=retained == attempt["centers"],
                methods=measures,
            )
        )
    return out


def replay(work, ident):
    from leo.analysis.starlink import acquisition

    lock = verified(work)["cases"][ident]
    _, policy, installed = capture_detector_lineage.source_lineage(_load_case(ident))
    if (
        installed["capture"]["root"] != lock["root"]
        or installed["capture"]["input_manifest_sha256"] != lock["input_manifest_sha256"]
        or any(_sha(Path(p)) != h for p, h in lock["installed_source"].items())
    ):
        raise ValueError("installed producer differs from source seal")
    screen = capture_starts.screen_module()
    bound = capture_bound.Envelope(work / "capture-bound.so")
    rows = []
    original = None
    for i, entry in enumerate(lock["windows"]):
        if "unavailable" in entry:
            rows.append(entry)
            continue
        window = case_window(work, entry)
        cases = pair(window, policy, bound, acquisition, screen, i, 2)
        audit = audit_window(window, policy, bound, acquisition, screen)
        rows.append(
            dict(visit=entry["visit"], iq_sha256=window.iq_sha256, pairs=cases, audit=audit)
        )
        if cases[0]["stock"]["status"] == "processed":
            original = window
        print(ident, entry["visit"], "pairs", len(cases), "audit", len(audit), flush=True)
    controls = {}
    signed = 720000 if lock["edge"] == "lower" else -720000
    if original is not None:
        for i, (key, plant) in enumerate(
            (
                ("signed", ((735, signed, 640),)),
                ("weak", ((735, 48000, 128),)),
                ("noise", ()),
                ("empty", ()),
            )
        ):
            synthetic = _test_signal(original, plant, 80214 + i)
            if key == "empty":
                raw = np.zeros_like(synthetic.samples)
                synthetic = iq_stream.IQWindow(
                    **{
                        **vars(synthetic),
                        "samples": raw,
                        "iq_sha256": iq_stream._digest(raw.tobytes()),
                    }
                )
            controls[key] = dict(
                plant=plant,
                iq_sha256=synthetic.iq_sha256,
                pairs=pair(synthetic, policy, bound, acquisition, screen, i, 1),
                audit=audit_window(synthetic, policy, bound, acquisition, screen),
            )
    write(
        work / f"{ident}.json.gz",
        gzip.compress(encoded(dict(cases=rows, controls=controls, installed=installed)), mtime=0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", *CASES))
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    root = local_output(args.work)
    if args.mode == "freeze":
        freeze(root)
    else:
        replay(root, args.mode)
