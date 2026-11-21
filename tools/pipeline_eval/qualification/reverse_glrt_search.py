"""Run the forward-blind and orbit-directed raw waveform comparisons on a frozen roster."""

import argparse
import ctypes as ct
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    edge_frequencies_hz,
    qin_edge_pilot_frame,
)
from ..variants import full_epoch_glrt as g
from ..variants.portable_field import Detector
from ..variants.verifier_integration import Result
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import ARMS, REPORT, digest, packed

WORK = Path("/srv/bulk/leo-dev/ds26-reverse-glrt-20261120")


def key(row):
    return f"{row['case']}-v{row['visit']:04d}-rx{row['rx']}"


def timed(fn, *args):
    cpu, wall = process_time(), perf_counter()
    answer = fn(*args)
    return answer, dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)


class Verifier:
    """Use the stock fractional GLRT at an independently nominated time and frequency."""

    def __init__(self, binary, edge, samples, lane):
        if ct.sizeof(Result) != 896:
            raise ValueError("unsupported verifier ABI")
        lib = self.lib = ct.CDLL(str(binary))
        lib.portable_verifier_create.argtypes = (ct.c_void_p, ct.c_void_p)
        lib.portable_verifier_create.restype = ct.c_void_p
        lib.portable_verifier_free.argtypes = (ct.c_void_p,)
        lib.portable_verifier_free.restype = None
        lib.portable_verifier_load.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_uint)
        lib.portable_verifier_glrt.argtypes = (ct.c_void_p, ct.c_uint, ct.POINTER(Result))
        self.templates = [
            np.ascontiguousarray(
                qin_edge_pilot_frame(g.RATE, edge, symbol_roll=r), dtype=np.complex128
            )
            for r in (0, CONTROL_SYMBOL_ROLL)
        ]
        self.ctx = lib.portable_verifier_create(*(c.ctypes.data for c in self.templates))
        if not self.ctx:
            raise MemoryError("verifier allocation")
        if lib.portable_verifier_load(self.ctx, samples.ctypes.data, lane) != 0:
            self.close()
            raise ValueError("invalid verifier input")

    def close(self):
        self.lib.portable_verifier_free(self.ctx)
        self.ctx = None

    def __call__(self, e, f):
        out = Result(acquired_hz=f)
        if self.lib.portable_verifier_glrt(self.ctx, e, ct.byref(out)) != 0:
            raise ValueError("verifier failed")
        complete = bool(out.flags & 4)
        return dict(
            complete=complete,
            gate=bool(out.flags & 2),
            integer_epoch=e,
            seed_hz=f,
            epoch=(e + out.offset_samples) % g.PERIOD if complete else None,
            hz=f + out.fractional_residual_hz if complete else None,
            exact=out.fractional_exact if complete else None,
            control=out.fractional_control if complete else None,
            margin=out.fractional_exact - out.fractional_control if complete else None,
        )


def distances(a, b):
    return abs((a["epoch"] - b["epoch"] + g.PERIOD / 2) % g.PERIOD - g.PERIOD / 2), abs(
        a["hz"] - b["hz"]
    )


def selected_curves(row):
    curves = []
    for arm in ARMS:
        own = row["owners"][arm]
        if own:
            curves.append(
                dict(
                    arm=arm,
                    source="published",
                    norad=own["norad"],
                    hz=own["prediction_hz"],
                    component=own["component"],
                )
            )
        for p in row["brackets"][arm]:
            curves.append(dict(arm=arm, source="bracket", **p))
    return curves


def compare(samples, edge, lo, hi, wide, wrong, row, verify):
    code, shuffled = g.pilot(edge), g.pilot(edge, True)
    cache = {}

    def measurement(e, f, frames):
        k = (e, f, int(frames[0]))
        if k not in cache:
            cache[k] = g.refine(samples, code, e, f, frames, lo, hi)
        return cache[k]

    stock_cache = {}

    def stock(decision):
        k = (decision["epoch"], decision["hz"])
        if k not in stock_cache:
            stock_cache[k] = verify(*k)
        return stock_cache[k]

    def evaluate(center):
        # Frequency-window selection and epoch selection are independent on odd frames.
        even, odd = (g.best(wide, k, center) for k in (0, 1))
        if even is None or odd is None:
            return None
        a = measurement(*even[:2], g.EVEN)
        b = measurement(*odd[:2], g.ODD)
        dt, df = distances(a, b)
        hz = np.array([a["hz"]])
        ep = np.array([a["epoch"]])
        held = float(g.powers(samples, code, ep, hz, g.ODD)[0, 0])
        sham = float(g.powers(samples, shuffled, ep, hz, g.ODD)[0, 0])
        official = stock(a)
        same_stock = official["complete"] and all(
            x <= limit for x, limit in zip(distances(a, official), (2, 1000), strict=True)
        )
        return dict(
            even=a,
            odd=b,
            held_at_even=held,
            wrong_at_even=sham,
            epoch_delta=dt,
            hz_delta=df,
            stock=official,
            stock_same_peak=same_stock,
            replicated=bool(
                dt <= 2 and df <= 1000 and same_stock and official["gate"] and held > sham
            ),
        )

    broad = evaluate(None)
    curves = selected_curves(row)
    by_branch = {}
    nominated = []
    for p in curves:
        aliases = []
        for lift, center in g.branches(p["hz"], lo, hi):
            pick = g.best(wide, 0, center)
            if pick is None:
                continue
            # Frequency bounds, including both off-grid endpoints, determine all rows searched.
            ids = np.flatnonzero(abs(wide.hz - center) <= g.WIDTH)
            interval = f"{ids[0]}-{ids[-1]}"
            if interval not in by_branch:
                by_branch[interval] = evaluate(center)
            aliases.append(dict(lift=lift, center=center, interval=interval))
        nominated.append(dict(**p, aliases=aliases))
    for p in nominated:
        controls = []
        for shift in (-18_000, 18_000):
            candidates = []
            for _, center in g.branches(p["hz"] + shift, lo, hi):
                h = g.best(wide, 0, center)
                if h is not None:
                    candidates.append((h[2], center))
            if candidates:
                _, center = max(candidates)
                controls.append(dict(shift=shift, center=center, result=evaluate(center)))
        p["controls"] = controls

    # The shuffled pilot receives the same full timing-frequency and two-partition search.
    wp = [g.best(wrong, k) for k in (0, 1)]
    wr = [
        g.refine(samples, shuffled, *h[:2], fr, lo, hi)
        for h, fr in zip(wp, (g.EVEN, g.ODD), strict=True)
    ]
    wt, wf = distances(*wr)
    wh = float(
        g.powers(samples, shuffled, np.array([wr[0]["epoch"]]), np.array([wr[0]["hz"]]), g.ODD)[
            0, 0
        ]
    )
    return dict(
        blind=broad,
        curves=nominated,
        branches=by_branch,
        wrong_blind=dict(even=wr[0], odd=wr[1], held_at_even=wh, epoch_delta=wt, hz_delta=wf),
    )


def cheap(samples, edge, lo, hi, verify):
    scan = g.compact(samples, edge, lo, hi)
    seeds = g.distinct(scan, 8)
    code = g.pilot(edge)
    results = []
    for e, f in seeds:
        p = g.refine(samples, code, e, f, g.EVEN, lo, hi, radius=6000, step=500, span=3)
        results.append(verify(p["epoch"], p["hz"]))
    passed = [r for r in results if r["gate"]]
    return dict(
        seeds=seeds, results=results, winner=max(passed, key=lambda r: r["margin"], default=None)
    )


def run_one(args):
    row, report, binary = args
    ident = key(row)
    report = Path(report)
    segment, manifest, w = decode(_load_case(row["case"]), row["visit"])
    if (
        w.acquisition["sample_start"] != row["counter"]
        or w.target["channel"] != row["channel"]
        or w.target["edge"] != row["edge"]
        or w.acquisition["quality_flags"]
        or not w.acquisition["complete"]
    ):
        raise ValueError("I/Q does not match the owned physical opportunity")
    raw = w.samples[:, row["rx"]]
    samples = np.asarray(raw[:, 0] + 1j * raw[:, 1], np.complex64)
    edge = row["edge"]
    center = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]
    offsets = edge_frequencies_hz(edge)
    half = min(800_000.0, g.RATE / 2 + center + min(offsets), g.RATE / 2 - center - max(offsets))
    lo, hi = center - half, center + half
    v = Verifier(binary, edge, w.samples, row["rx"])
    try:
        with Detector(binary, edge) as original:
            original_result, original_time = timed(original, w, w.receiver_ids)
            lane = original_result[row["rx"]]
            passed = [
                c
                for c in lane.candidates
                if c.fractional_margin is not None and c.fractional_margin >= 0.025
            ]
            old = max(passed, key=lambda c: (c.fractional_margin, -c.candidate_rank), default=None)
            same_gate = (old is None) == (row["incumbent"] is None)
            old_df = (
                old.fractional_tracking_cfo_hz - row["incumbent"]["fractional_tracking_cfo_hz"]
                if old and row["incumbent"]
                else None
            )
            original_stages = [
                {k: item[k] for k in ("lane", "anchors", "coarse_cpu_ns", "verify_cpu_ns")}
                for item in original.attempts
            ]
        compact, compact_time = timed(cheap, samples, edge, lo, hi, v)
        wide, wide_time = timed(g.reference, samples, edge, lo, hi)
        frames = np.arange(14)
        wrong, wrong_time = timed(
            lambda: g.sweep(
                samples,
                g.pilot(edge, True),
                rate=g.RATE,
                first=g.FIRST,
                frames=frames,
                split=frames % 2,
                hz=wide.hz,
                nfft=g.NFFT,
            )
        )
        result, compare_time = timed(compare, samples, edge, lo, hi, wide, wrong, row, v)
    finally:
        v.close()
    grid_path = report / "grids" / (ident + ".npz")
    tmp_grid = grid_path.with_suffix(".partial.npz")
    np.savez_compressed(
        tmp_grid,
        hz=wide.hz,
        exact_epoch=wide.epochs,
        exact_score=wide.scores,
        wrong_epoch=wrong.epochs,
        wrong_score=wrong.scores,
    )
    tmp_grid.replace(grid_path)
    record = dict(
        key=ident,
        case=row["case"],
        visit=row["visit"],
        rx=row["rx"],
        row_id=row["id"],
        signed_iq=w.iq_sha256,
        segment=segment,
        sequence=w.sequence,
        manifest=manifest,
        interval_hz=[lo, hi],
        stratum=row["stratum"],
        old_pass=row["old_pass"],
        edge=edge,
        cpu=dict(
            original_stereo=original_time,
            original_stages=original_stages,
            compact_mono=compact_time,
            exact_grid=wide_time,
            wrong_grid=wrong_time,
            comparison=compare_time,
        ),
        grid=dict(
            integer_epochs=g.PERIOD,
            frequencies=len(wide.hz),
            step_hz=2 * g.RATE / g.NFFT,
            frames_per_partition=7,
        ),
        grid_sha256=_sha(grid_path),
        old_replay_same_gate=same_gate,
        old_replay_delta_hz=old_df,
        incumbent=row["incumbent"],
        compact=compact,
        **result,
    )
    path = report / "measurements" / (ident + ".json")
    tmp = path.with_suffix(".partial")
    tmp.write_bytes(packed(record) + b"\n")
    tmp.replace(path)
    return ident


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--case", choices=None)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    report = args.report
    for folder in ("measurements", "grids"):
        (report / folder).mkdir(exist_ok=True, parents=True)
    from .portable_field_run import build

    args.work.mkdir(exist_ok=True, parents=True)
    build_seal = args.work / "reverse-build.json"
    if not build_seal.exists():
        info = build(args.work)
        build_seal.write_bytes(packed(info))
    info = json.loads(build_seal.read_bytes())
    binary = Path(info["binary"]["path"])
    if _sha(binary) != info["binary"]["sha256"] or any(
        _sha(Path(p)) != s for p, s in info["sources"].items()
    ):
        raise ValueError("portable verifier build changed")
    roster = (report / "roster.json").read_bytes()
    manifest = json.loads((report / "manifest.json").read_bytes())
    if digest(roster) != manifest["roster_sha256"]:
        raise ValueError("roster changed")
    rows = [r for r in json.loads(roster) if args.case is None or r["case"] == args.case]
    if args.limit:
        rows = rows[: args.limit]
    paths = [Path(__file__), Path(g.__file__), Path(decode.__code__.co_filename)]
    lock = dict(
        roster_sha256=digest(roster),
        sources={p.name: _sha(p) for p in paths},
        binary=info["binary"]["sha256"],
        native_sources=info["sources"],
    )
    receipt = report / "search-lock.json"
    if (
        receipt.exists()
        and json.loads(receipt.read_bytes()) != lock
        and any((report / "measurements").glob("*.json"))
    ):
        raise ValueError("search source changed; select a fresh output directory")
    receipt.write_bytes(packed(lock) + b"\n")
    pending = [
        (r, report, binary)
        for r in rows
        if not (report / "measurements" / (key(r) + ".json")).exists()
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run_one, pending):
            print(result, flush=True)


if __name__ == "__main__":
    main()
