"""Find multiple split-stable signed waveform peaks from the receiver-independent dense grids."""

import argparse
import json
import os
import zipfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..variants import full_epoch_glrt as g
from ..variants.two_carrier import same
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import Verifier, key
from .reverse_quarter_trial import null_samples
from .timing_first_roster import OUT as PREVIOUS
from .timing_first_trial import inventories
from .two_carrier_position import ORIGINAL
from .two_carrier_roster import OUT
from .two_carrier_trial import from_archive


def dt(a, b):
    return abs((a - b + g.PERIOD / 2) % g.PERIOD - g.PERIOD / 2)


def shortlist(sweep, half, limit=6):
    score = sweep.scores[:, half, :]
    order = np.argsort(-score.ravel(), kind="stable")
    chosen = []
    for idx in order:
        i, j = np.unravel_index(idx, score.shape)
        e, f = int(sweep.epochs[i, half, j]), float(sweep.hz[i])
        if all(dt(e, p[0]) > 5 or abs(f - p[1]) > 8000 for p in chosen):
            chosen.append((e, f))
            if len(chosen) == limit:
                break
    return chosen


def adjudicate(samples, code, sham, sweep, verify=None):
    a, b = [shortlist(sweep, k) for k in (0, 1)]
    lo, hi = float(sweep.hz[0]), float(sweep.hz[-1])
    cache = {}

    def refine(k, i):
        if (k, i) not in cache:
            e, f = (a, b)[k][i]
            cache[k, i] = g.refine(samples, code, e, f, (g.EVEN, g.ODD)[k], lo, hi)
        return cache[k, i]

    proposals = []
    for i, (e, f) in enumerate(a):
        for j, (o, h) in enumerate(b):
            if dt(e, o) > 6 or abs(f - h) > 4000:
                continue
            even, odd = refine(0, i), refine(1, j)
            if not same(even, odd):
                continue
            ep = np.array([even["epoch"]])
            hz = np.array([even["hz"]])
            held = float(g.powers(samples, code, ep, hz, g.ODD)[0, 0])
            wrong = float(g.powers(samples, sham, ep, hz, g.ODD)[0, 0])
            if held <= wrong:
                continue
            official = verify(even["epoch"], even["hz"]) if verify else None
            accepted = bool(official and official["gate"] and same(even, official))
            proposals.append(
                dict(
                    even_rank=i + 1,
                    odd_rank=j + 1,
                    even=even,
                    odd=odd,
                    held=held,
                    shuffled_at_candidate=wrong,
                    official=official,
                    accepted=accepted,
                )
            )
    used_a, used_b, rows = set(), set(), []
    for p in sorted(
        proposals,
        key=lambda q: (
            not q["accepted"],
            max(q["even_rank"], q["odd_rank"]),
            -min(q["even"]["score"], q["odd"]["score"]),
        ),
    ):
        i, j = p["even_rank"], p["odd_rank"]
        if i in used_a or j in used_b or any(same(p["even"], prev["even"]) for prev in rows):
            continue
        used_a.add(i)
        used_b.add(j)
        rows.append(p)
    return rows


def part(job):
    entries, cpu, folder, archives = job
    os.sched_setaffinity(0, {cpu})
    with ExitStack() as resources:
        bank = {}
        for path in archives:
            z = resources.enter_context(zipfile.ZipFile(path))
            for item in json.loads(z.read("index.json"))["visits"]:
                bank[item["key"]] = z, item
        for r, folder_old, scope, cohort in entries:
            name = key(r)
            dest = folder / scope / (name + ".json")
            if dest.exists():
                continue
            old = read(folder_old / "measurements" / (name + ".json"))
            w = (
                from_archive(r, bank[name])
                if name in bank
                else decode(_load_case(r["case"]), r["visit"])[2]
            )
            if w.iq_sha256 != old["signed_iq"] or r["counter"] != w.acquisition["sample_start"]:
                raise ValueError("signed measurement changed")
            iq = w.samples if scope != "null" else null_samples(w.samples, int(r["id"][-12:], 16))
            x = np.asarray(iq[:, r["rx"], 0] + 1j * iq[:, r["rx"], 1], np.complex64)
            p = folder_old / "grids" / (name + ".npz")
            sha = _sha(p)
            if sha != old["grid_sha256"]:
                raise ValueError("independent frequency or timing grid changed")
            codes = [g.pilot(r["edge"], shuffled) for shuffled in (False, True)]
            with np.load(p) as grid:
                if scope == "null":
                    frames = np.arange(14)
                    sweeps = [
                        g.sweep(
                            x,
                            code,
                            rate=g.RATE,
                            first=g.FIRST,
                            frames=frames,
                            split=frames % 2,
                            hz=grid["hz"],
                            nfft=g.NFFT,
                        )
                        for code in codes
                    ]
                else:
                    sweeps = [
                        g.Sweep(grid["hz"], grid[k + "_epoch"], grid[k + "_score"])
                        for k in ("exact", "wrong")
                    ]
            proof = Verifier(ORIGINAL, r["edge"], iq, r["rx"])
            try:
                real = adjudicate(x, *codes, sweeps[0], proof)
                shuffled = adjudicate(x, codes[1], codes[0], sweeps[1])
            finally:
                proof.close()
            got_primary = any(
                v["accepted"] and v["even_rank"] == 1 and v["odd_rank"] == 1 for v in real
            )
            if scope != "null" and got_primary != old["blind"]["replicated"]:
                raise ValueError(
                    f"multi-reference changed the original strongest-peak decision on {name}"
                )
            tmp = dest.with_suffix(".partial")
            tmp.write_bytes(
                packed(
                    dict(
                        key=name,
                        scope=scope,
                        cohort=cohort,
                        iq="sha256:" + digest(iq.tobytes()),
                        raw_iq=w.iq_sha256,
                        frequencies=len(sweeps[0].hz),
                        lo_hz=float(sweeps[0].hz[0]),
                        hi_hz=float(sweeps[0].hz[-1]),
                        original_grid_sha256=sha,
                        real=real,
                        shuffled=shuffled,
                    )
                )
                + b"\n"
            )
            tmp.replace(dest)


def run(out, cpus):
    root = out / "multipeak"
    panels = dict(inventories(PREVIOUS), prospective=out / "prospective")
    jobs = []
    pros = {}
    for cohort, folder in panels.items():
        if _sha(folder / "roster.json") != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("roster changed")
        for r in read(folder / "roster.json"):
            jobs.append((r, folder, "ordinary", cohort))
            if cohort in ("development", "replication", "heldout", "quarter_holdout", "recovery"):
                wide = PREVIOUS / (
                    "reverse-physical-reference" if cohort == "recovery" else "physical-reference"
                )
                jobs.append((r, wide, "physical", cohort))
            if cohort == "prospective":
                pros.setdefault(r["case"], []).append(r)
    for pool in pros.values():
        for r in sorted(pool, key=lambda r: digest(packed(["two-carrier-null-v1", r["id"]])))[:5]:
            jobs.append((r, panels["prospective"], "null", "prospective"))
    for s, n in (("ordinary", 469), ("physical", 229), ("null", 40)):
        assert sum(j[2] == s for j in jobs) == n
        (root / s).mkdir(parents=True, exist_ok=True)
    source = read(PREVIOUS / "iq-bundles.json")
    if any(_sha(Path(r["path"])) != r["sha256"] for r in source.values()):
        raise ValueError("archived inputs changed")
    archives = [Path(r["path"]) for r in source.values()]
    lock = dict(
        source=_sha(Path(__file__)),
        protocol=_sha(out / "MULTIPEAK-REFERENCE.md"),
        core=_sha(Path(g.__file__)),
        original=_sha(ORIGINAL),
        rosters={k: _sha(v / "roster.json") for k, v in panels.items()},
    )
    seal = root / "source-lock.json"
    if seal.exists() and read(seal) != lock:
        raise ValueError("independent reference inputs changed")
    seal.write_bytes(packed(lock) + b"\n")
    jobs.sort(key=lambda j: digest(packed([j[0]["id"], j[2]])))
    with ProcessPoolExecutor(max_workers=len(cpus)) as workers:
        list(
            workers.map(
                part, [(jobs[i :: len(cpus)], c, root, archives) for i, c in enumerate(cpus)]
            )
        )
    print("verified multi-peak references", len(jobs), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--cpus", type=int, nargs="+", default=[10, 12, 14, 16, 18, 20])
    a = p.parse_args()
    run(a.report, a.cpus)
