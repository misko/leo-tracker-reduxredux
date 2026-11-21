"""Use held symbols to test whether stronger pilots explain other repeatable carriers."""

import argparse
import json
import os
import zipfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from ..variants import full_epoch_glrt as g
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import Verifier, key
from .reverse_quarter_trial import null_samples
from .timing_first_report import tab
from .timing_first_roster import OUT as PREVIOUS
from .timing_first_trial import inventories
from .two_carrier_injections import mix, unit_wave
from .two_carrier_position import ORIGINAL
from .two_carrier_reference import adjudicate
from .two_carrier_roster import OUT
from .two_carrier_trial import from_archive

J = np.arange(64 * 44)
FRAMES = np.arange(14)
ORDER = np.random.default_rng(51961).permutation(64)


def atom(template, measured, n):
    ticks = 3 * n - round(3 * measured["epoch"])
    frames, phase = np.divmod(ticks, 40000)
    # Each frame has its own complex gain, so its common carrier phase drops out.
    rotor = np.exp(2j * np.pi * measured["hz"] * J / 1e7)
    return template[phase] * rotor, frames


def predictive_gain(x, template, target, stronger):
    epoch = round(3 * target["epoch"])
    starts = (epoch + 40000 * FRAMES + 264 + 2) // 3
    n = starts[:, None] + J
    y = x[n]
    wanted, _ = atom(template, target, n)
    # Permute the transmitted symbols while retaining their actual carrier phase.
    shifted = np.exp(2j * np.pi * target["hz"] * J / 1e7)
    unmod = wanted / shifted
    wrong = unmod.reshape(14, 64, 44)[:, ORDER, :].reshape(14, -1) * shifted
    delta = np.exp(2j * np.pi * 18000 * J / 1e7)
    bank = np.stack((wanted, wrong, wanted * delta, wanted * delta.conj()), axis=-1)
    others = [atom(template, s, n) for s in stronger]
    gain = np.zeros((2, 2, 4))
    energy = np.zeros((2, 2))
    ident = np.zeros((2, 2))
    original = np.zeros((2, 2))
    for frame in range(14):
        cols = [np.ones(len(J), dtype=complex)]
        for waveform, period in others:
            for j in np.unique(period[frame]):
                v = np.where(period[frame] == j, waveform[frame], 0.0)
                if np.any(v):
                    cols.append(v)
        H = np.stack(cols, axis=1)
        Z = np.column_stack((y[frame], bank[frame]))
        for train in (0, 1):
            sel = train == (J // 44) % 2
            h, hh = H[sel], H[~sel]
            z, zz = Z[sel], Z[~sel]
            # Fit all nuisance projections together. A complex least-squares fit
            # for each trial column then measures its incremental held-symbol power.
            gram = h.conj().T @ h
            coef = np.linalg.lstsq(gram, h.conj().T @ z, rcond=1e-9)[0]
            clean = z - h @ coef
            held = zz - hh @ coef
            b = clean[:, 1:]
            bh = held[:, 1:]
            norm = np.sum(abs(b) ** 2, axis=0)
            a = np.sum(b.conj() * clean[:, :1], axis=0) / np.maximum(norm, 1e-20)
            prev = held[:, :1]
            reduction = np.sum(abs(prev) ** 2 - abs(prev - bh * a) ** 2, axis=0)
            idx = (frame % 2, train)
            gain[idx] += reduction
            energy[idx] += float(np.sum(abs(zz[:, 0]) ** 2))
            ident[idx] += norm[0]
            original[idx] += float(np.sum(abs(z[:, 1]) ** 2))
    effect = gain / np.maximum(energy[:, :, None], 1e-20)
    fraction = ident / np.maximum(original, 1e-20)
    separation = effect[:, :, 0] - np.maximum(0, np.max(effect[:, :, 1:], axis=2))
    return dict(
        passed=bool(np.all(separation > 0) and np.min(fraction) >= 0.001),
        min_increment=float(np.min(effect[:, :, 0])),
        min_lead=float(np.min(separation)),
        min_distinguishable=float(np.min(fraction)),
        gain=effect.tolist(),
    )


def labels(x, edge, rows):
    template = qin_edge_pilot_frame(30000000, edge)
    qualified = sorted(
        (r for r in rows if r["accepted"]),
        key=lambda r: -min(r["even"]["score"], r["odd"]["score"]),
    )
    previous = []
    out = []
    for r in qualified:
        p = {k: r["official"][k] for k in ("epoch", "hz")}
        base = predictive_gain(x, template, p, [])
        conditioned = predictive_gain(x, template, p, previous) if previous else base
        # Require both tests so suppression cannot create a new positive label.
        keep = base["passed"] and conditioned["passed"]
        out.append(
            dict(
                even=r["even"],
                target=p,
                kept=keep,
                stronger=len(previous),
                unconditioned=base,
                conditional=conditioned,
            )
        )
        if keep:
            previous.append(p)
    return out


def injection(r, w, meta):
    seed = int(meta["seed"])
    rng = np.random.default_rng(seed)
    original = null_samples(w.samples, int(rng.integers(2**48)))
    tick = int(rng.integers(40000))
    gap = int(meta["frequency_separation_hz"])
    tick2 = (tick + 12001) % 40000 if meta["separated"] == "True" else tick
    template = qin_edge_pilot_frame(30000000, r["edge"])
    a, t1 = unit_wave(template, tick, float(meta["primary_hz"]), seed + 1, gap == 227000)
    waves = [(a, -15)]
    truth = [t1]
    if meta["secondary_snr_db"]:
        b, t2 = unit_wave(template, tick2, float(meta["secondary_hz"]), seed + 2, gap == 40000)
        waves.append((b, float(meta["secondary_snr_db"])))
        truth.append(t2)
    raw, _ = mix(original, r["rx"], waves)
    if "sha256:" + digest(raw.tobytes()) != meta["iq"]:
        raise ValueError("planted mixture does not reproduce")
    return raw, truth


def part(job):
    items, cpu, out, archives = job
    os.sched_setaffinity(0, {cpu})
    with ExitStack() as resources:
        bank = {}
        for p in archives:
            z = resources.enter_context(zipfile.ZipFile(p))
            for v in json.loads(z.read("index.json"))["visits"]:
                bank[v["key"]] = z, v
        for r, scope, meta in items:
            ident = key(r) if scope != "injection" else meta["iq"][7:]
            dest = out / "conditional" / scope / (ident + ".json")
            if dest.exists():
                continue
            name = key(r)
            if scope != "injection":
                src = out / "multipeak" / scope / (ident + ".json")
                previous = read(src)
                if not any(v["accepted"] for v in previous["real"]):
                    dest.write_bytes(
                        packed(
                            dict(
                                key=ident,
                                scope=scope,
                                iq=previous["iq"],
                                source=_sha(src),
                                labels=[],
                            )
                        )
                        + b"\n"
                    )
                    continue
            w = (
                from_archive(r, bank[name])
                if name in bank
                else decode(_load_case(r["case"]), r["visit"])[2]
            )
            if scope == "injection":
                raw, truth = injection(r, w, meta)
            else:
                raw = (
                    w.samples
                    if scope != "null"
                    else null_samples(w.samples, int(r["id"][-12:], 16))
                )
                truth = None
            rx = r["rx"]
            x = np.asarray(raw[:, rx, 0] + 1j * raw[:, rx, 1], np.complex64)
            sha = "sha256:" + digest(raw.tobytes())
            if scope != "injection":
                if sha != previous["iq"]:
                    raise ValueError("conditional test received different I/Q")
                candidates = previous["real"]
                decoy = previous["shuffled"]
            else:
                sw = g.reference(x, r["edge"], -800000, 800000)
                frames = np.arange(14)
                code, sham = g.pilot(r["edge"]), g.pilot(r["edge"], True)
                wrong = g.sweep(
                    x,
                    sham,
                    rate=g.RATE,
                    first=g.FIRST,
                    frames=frames,
                    split=frames % 2,
                    hz=sw.hz,
                    nfft=g.NFFT,
                )
                proof = Verifier(ORIGINAL, r["edge"], raw, rx)
                try:
                    candidates = adjudicate(x, code, sham, sw, proof)
                finally:
                    proof.close()
                decoy = adjudicate(x, sham, code, wrong)
            tests = labels(x, r["edge"], candidates)
            tmp = dest.with_suffix(".partial")
            tmp.write_bytes(
                packed(
                    dict(
                        key=ident,
                        scope=scope,
                        case=r["case"],
                        visit=r["visit"],
                        rx=rx,
                        iq=sha,
                        source=_sha(src) if scope != "injection" else meta["source_id"],
                        truth=truth,
                        decoy_repeats=len(decoy),
                        labels=tests,
                    )
                )
                + b"\n"
            )
            tmp.replace(dest)


def run(out, cpus):
    panels = dict(inventories(PREVIOUS), prospective=out / "prospective")
    roster = {key(r): r for folder in panels.values() for r in read(folder / "roster.json")}
    byid = {r["id"]: r for r in roster.values()}
    inputs = tab(out / "injections.csv")
    jobs = []
    for scope in ("ordinary", "physical", "null", "injection"):
        (out / "conditional" / scope).mkdir(parents=True, exist_ok=True)
        if scope == "injection":
            jobs.extend(
                (byid[r["source_id"]], scope, r) for r in inputs if r["method"] == "original"
            )
        else:
            jobs.extend(
                (roster[p.stem], scope, None) for p in (out / "multipeak" / scope).glob("DS*.json")
            )
    if len(jobs) != 818:
        raise ValueError("missing reference or injection inputs")
    lock = dict(
        protocol=_sha(out / "CONDITIONAL.md"),
        source=_sha(Path(__file__)),
        reference=_sha(out / "multipeak/source-lock.json"),
        injection_table=_sha(out / "injections.csv"),
    )
    seal = out / "conditional" / "source-lock.json"
    if seal.exists() and read(seal) != lock:
        raise ValueError("conditional criteria changed during replay")
    seal.write_bytes(packed(lock) + b"\n")
    jobs.sort(key=lambda j: digest(packed([j[0]["id"], j[1], j[2]["iq"] if j[2] else ""])))
    archives = [Path(r["path"]) for r in read(PREVIOUS / "iq-bundles.json").values()]
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        list(pool.map(part, [(jobs[i :: len(cpus)], c, out, archives) for i, c in enumerate(cpus)]))
    print("verified conditional pilot predictions in", len(jobs), "grids", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--cpus", type=int, nargs="+", default=[8, 10, 12, 14, 16, 18, 20, 22])
    a = p.parse_args()
    run(a.report, a.cpus)
