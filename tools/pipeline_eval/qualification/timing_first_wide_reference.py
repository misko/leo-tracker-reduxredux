"""Extend every frozen timing/frequency search to the hardware-supported signed carrier band."""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import edge_frequencies_hz

from ..variants import full_epoch_glrt as g
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import REPORT, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import WORK, Verifier, compare, key
from .timing_first_roster import OUT

PANELS = ("", "heldout", "replication", "quarter-holdout")


def physical_bounds(window, edge):
    bw = min(
        float(json.loads(window.acquisition["retune_receipt"])["analog_bandwidth_hz"]),
        window.sample_rate_hz,
    )
    offsets = edge_frequencies_hz(edge)
    return -bw / 2 - float(min(offsets)), bw / 2 - float(max(offsets))


def complete_grid(samples, code, prior, grid, lo, hi):
    hz = g.frequency_grid(lo, hi, 2 * g.RATE / g.NFFT)
    missing = hz[~np.isin(hz, prior.hz)]
    frames = np.arange(14)
    added = g.sweep(
        samples,
        code,
        rate=g.RATE,
        first=g.FIRST,
        frames=frames,
        split=frames % 2,
        hz=missing,
        nfft=g.NFFT,
    )
    combined = np.r_[prior.hz, added.hz]
    order = np.argsort(combined, kind="stable")
    together = g.Sweep(
        combined[order],
        np.concatenate([prior.epochs, added.epochs])[order],
        np.concatenate([prior.scores, added.scores])[order],
    )
    if not np.all(np.diff(together.hz) > 0) or together.hz[0] != lo or together.hz[-1] != hi:
        raise ValueError("physical CFO coverage has missing endpoints or duplicate cells")
    grid.append((len(prior.hz), len(missing), len(together.hz)))
    return together


def investigate(job):
    row, panel, source, dest, work = job
    ident = key(row)
    path = dest / "measurements" / (ident + ".json")
    if path.exists():
        return ident
    folder = source / panel
    earlier = read(folder / "measurements" / (ident + ".json"))
    old_grid = folder / "grids" / (ident + ".npz")
    if earlier["row_id"] != row["id"] or _sha(old_grid) != earlier["grid_sha256"]:
        raise ValueError("nominal acquisition grid changed")
    _, manifest, w = decode(_load_case(row["case"]), row["visit"])
    if not (
        w.iq_sha256 == earlier["signed_iq"]
        and w.acquisition["sample_start"] == row["counter"]
        and manifest == earlier["manifest"]
        and w.target["edge"] == row["edge"]
    ):
        raise ValueError("raw capture differs from original benchmark")
    lo, hi = physical_bounds(w, row["edge"])
    raw = w.samples[:, row["rx"]]
    x = np.empty(len(raw), np.complex64)
    x.real = raw[:, 0]
    x.imag = raw[:, 1]
    counts = []
    with np.load(old_grid) as prior:
        grids = [
            complete_grid(
                x,
                g.pilot(row["edge"], wrong),
                g.Sweep(prior["hz"], prior[name + "_epoch"], prior[name + "_score"]),
                counts,
                lo,
                hi,
            )
            for wrong, name in ((False, "exact"), (True, "wrong"))
        ]
    if counts[0] != counts[1]:
        raise ValueError("wrong pilot received a different search budget")
    verifier = Verifier(work / "portable-field.so", row["edge"], w.samples, row["rx"])
    try:
        result = compare(x, row["edge"], lo, hi, *grids, row, verifier)
    finally:
        verifier.close()
    e, b = grids
    target = dest / "grids" / (ident + ".npz")
    np.savez_compressed(
        target,
        hz=e.hz,
        exact_epoch=e.epochs,
        exact_score=e.scores,
        wrong_epoch=b.epochs,
        wrong_score=b.scores,
    )
    meta = dict(
        key=ident,
        panel=panel or "initial",
        case=row["case"],
        visit=row["visit"],
        rx=row["rx"],
        row_id=row["id"],
        signed_iq=w.iq_sha256,
        grid_sha256=_sha(target),
        reused_grid_sha256=earlier["grid_sha256"],
        bounds=[lo, hi],
        frequency_counts=counts[0],
        integer_epochs=g.PERIOD,
        **result,
    )
    tmp = path.with_suffix(".partial")
    tmp.write_bytes(packed(meta) + b"\n")
    tmp.replace(path)
    return ident


def run(source, report, work, workers):
    dest = report / "physical-reference"
    for folder in ("measurements", "grids"):
        (dest / folder).mkdir(parents=True, exist_ok=True)
    hashes = {}
    jobs = []
    for panel in PANELS:
        path = source / panel / "roster.json"
        fingerprint = _sha(path)
        if fingerprint != read(path.parent / "manifest.json")["roster_sha256"]:
            raise ValueError("physical reference roster changed")
        hashes[panel or "initial"] = fingerprint
        jobs.extend((r, panel, source, dest, work) for r in read(path))
    if len(jobs) != len({(r["case"], r["visit"]) for r, *_ in jobs}):
        raise ValueError("duplicate physical visit")
    lock = dict(
        source=_sha(Path(__file__)),
        template=_sha(Path(g.__file__)),
        verifier=_sha(work / "portable-field.so"),
        comparison=_sha(Path(compare.__code__.co_filename)),
        rosters=hashes,
        protocol=_sha(OUT / "PROTOCOL.md"),
    )
    receipt = dest / "source-lock.json"
    if receipt.exists() and read(receipt) != lock:
        raise ValueError("physical receiver reference lock changed")
    receipt.write_bytes(packed(lock) + b"\n")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(investigate, jobs), 1):
            if i % 20 == 0:
                print("physical direct and shuffled references", i, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--source", type=Path, default=REPORT)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    run(a.source, a.report, a.work, a.workers)
