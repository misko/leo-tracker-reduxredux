"""Blind-to-site directional forecast validation on held catalogue dates and NORADs."""

import argparse
import gzip
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np

from leo.sky.frames import julian_day_from_utc_ns

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import phase_forecast as law
from . import phase_forecast_history as history

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/redesign/phase-forecast"
DEFAULT_STORE = Path("/mnt/qnap01/mouse9911/tle")
DATES = ("2026-10-16", "2026-10-22", "2026-10-28", "2026-11-03", "2026-11-09", "2026-11-15")
SALT = "phase-forecast/20261119/"
SAT_PER_DATE = 512
CPUS = (8, 9)
H = law.HOUR


def digest(raw):
    return sha256(raw).hexdigest()


def stamp(dt):
    return int(dt.timestamp()) * law.SECOND + dt.microsecond * 1000


def manifest(store, target):
    center = datetime.fromtimestamp(target / law.SECOND, UTC)
    out = []
    for offset in range(-3, 3):
        date = (center + timedelta(days=offset)).strftime("%Y/%m/%d")
        folder = store / "snapshots/space-track/starlink" / date
        for p in sorted(folder.glob("*.json")):
            row = json.loads(p.read_bytes())
            collection = stamp(datetime.fromisoformat(row["retrieved_at"]))
            if target - 72 * H <= collection <= target + 48 * H:
                out.append(
                    dict(
                        collection_ns=collection,
                        sha256=row["raw_sha256"],
                        path=str(store / row["raw_object"]),
                        receipt=p.name,
                    )
                )
    return sorted(out, key=lambda row: row["collection_ns"])


def proxy(current, following, target):
    if law.epoch_ns(following) <= target + 300 * law.SECOND:
        raise ValueError("proxy element is within the target or in the causal past")
    j, f = julian_day_from_utc_ns(np.asarray([target], dtype=np.int64))
    a, position, v = current.sgp4(float(j[0]), float(f[0]))
    b, later, _ = following.sgp4(float(j[0]), float(f[0]))
    if a or b:
        return None
    value, transverse = law.phase_delta(np.asarray(position), np.asarray(v), np.asarray(later))
    return (float(value), float(transverse)) if np.isfinite([value, transverse]).all() else None


def measure(index, store):
    date = DATES[index]
    target = stamp(datetime.fromisoformat(date + "T12:15:00+00:00"))
    frames = manifest(store, target)
    before = [r for r in frames if r["collection_ns"] <= target]
    later = [r for r in frames if target < r["collection_ns"]]
    current_file = before[-1]
    eligible, sources = {}, {}
    for number, sat, pair in history.satellites(history.available(current_file)):
        key = int(digest((SALT + str(number)).encode())[:16], 16)
        epoch = law.epoch_ns(sat)
        if (
            key % len(DATES) == index
            and target - 48 * H <= epoch <= current_file["collection_ns"]
            and (number not in eligible or epoch > law.epoch_ns(eligible[number][1]))
        ):
            eligible[number] = (key, sat, pair)
    roster = sorted(eligible, key=lambda k: eligible[k][0])[:SAT_PER_DATE]
    current = [eligible[n][1] for n in roster]
    document = dict(
        anchor_utc_ns=target,
        cutoff_utc_ns=target,
        catalog_timestamp_ns=current_file["collection_ns"],
    )
    previous = history.predecessors(current, document, list(reversed(before[:-1])), sources)
    signed = law.mean_forecast(current, previous, document)
    # Risk predictions are complete before later elements are opened.
    subsequent, later_seen, used = {}, {current_file["sha256"]}, []
    for item in later:
        if item["sha256"] in later_seen:
            continue
        later_seen.add(item["sha256"])
        remaining = set(roster) - subsequent.keys()
        if not remaining:
            break
        candidates = {}
        for n, sat, pair in history.satellites(history.available(item), remaining):
            epoch = law.epoch_ns(sat)
            if not target + 300 * law.SECOND < epoch <= item["collection_ns"]:
                continue
            if n not in candidates or epoch < candidates[n][1]:
                candidates[n] = (sat, epoch, item["collection_ns"], pair)
        used.append(item)
        subsequent.update(candidates)
    rows = []
    for n, sat, prediction in zip(roster, current, signed, strict=True):
        prev, next_ = previous.get(n), subsequent.get(n)
        exact = proxy(sat, next_[0], target) if next_ else None
        no_proxy = (
            "no_later_element" if next_ is None else "propagation_failed" if exact is None else None
        )
        rows.append(
            dict(
                date=date,
                norad=n,
                capture_utc_ns=target,
                current_epoch_ns=law.epoch_ns(sat),
                current_pair_sha256=eligible[n][2],
                current_collected_ns=current_file["collection_ns"],
                predecessor=dict(
                    zip(("epoch_ns", "collection_ns", "pair_sha256"), prev[1:], strict=True)
                )
                if prev
                else None,
                later=dict(
                    zip(("epoch_ns", "collection_ns", "pair_sha256"), next_[1:], strict=True)
                )
                if next_
                else None,
                mean_phase_s=float(prediction),
                proxy_phase_s=exact[0] if exact else None,
                proxy_transverse_km=exact[1] if exact else None,
                missing_proxy=no_proxy,
            )
        )
    return rows, dict(date=date, current=current_file, causal_history=sources, later_snapshots=used)


def summarize(rows):
    paired = [r for r in rows if r["proxy_phase_s"] is not None]
    target = np.array([r["proxy_phase_s"] for r in paired])
    signed = np.array([r["mean_phase_s"] for r in paired])
    strong = abs(target) >= 0.5
    active = abs(signed) > 0
    matched = strong & active
    if not paired:
        raise ValueError("no eligible retrospective proxy")

    def stats(model):
        delta = target - model
        return dict(
            rms_s=float(np.sqrt(np.mean(delta**2))),
            mae_s=float(np.mean(abs(delta))),
            median_abs_s=float(np.median(abs(delta))),
            strong_sign_correct=int(
                np.count_nonzero(np.sign(target[strong]) == np.sign(model[strong]))
            ),
            active_strong_sign_correct=int(
                np.count_nonzero(np.sign(target[matched]) == np.sign(model[matched]))
            ),
        )

    return dict(
        attempted=len(rows),
        paired=len(paired),
        predicted_nonzero=int(active.sum()),
        signed_proxy_correlation=float(np.corrcoef(signed, target)[0, 1])
        if np.any(signed)
        else None,
        predicted_strong=int(matched.sum()),
        proxy_strong=int(strong.sum()),
        missing=dict(Counter(r["missing_proxy"] for r in rows if r["missing_proxy"])),
        zero=stats(np.zeros_like(target)),
        signed=stats(signed),
        opposite_sign_placebo=stats(-signed),
    )


def lane(task):
    cpu, ids, store = task
    os.sched_setaffinity(0, {cpu})
    records = []
    for i in ids:
        began = perf_counter()
        rows, inputs = measure(i, store)
        print(
            DATES[i],
            len(rows),
            sum(r["proxy_phase_s"] is not None for r in rows),
            round(perf_counter() - began, 2),
            flush=True,
        )
        records.append((rows, inputs))
    return records


def run(store):
    paths = [Path(__file__), Path(history.__file__), Path(law.__file__), OUTPUT / "PROTOCOL.md"]
    frozen = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}
    plan = dict(
        cpus=list(CPUS), sources=frozen, dates=list(DATES), salt=SALT, cap_per_date=SAT_PER_DATE
    )
    save_json(OUTPUT / "catalogue-plan.json", plan)
    began = perf_counter()
    with ProcessPoolExecutor(2) as pool:
        groups = pool.map(
            lane, [(cpu, list(range(i, len(DATES), 2)), store) for i, cpu in enumerate(CPUS)]
        )
        records = sorted([entry for group in groups for entry in group], key=lambda p: p[1]["date"])
    if {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths} != frozen:
        raise ValueError("forecast source changed after protocol lock")
    rows = [row for part, _ in records for row in part]
    dates = {source["date"]: summarize(part) for part, source in records}
    pooled = summarize(rows)
    pooled_reduction = 1 - pooled["signed"]["rms_s"] / pooled["zero"]["rms_s"]
    gains = sum(r["signed"]["rms_s"] < r["zero"]["rms_s"] for r in dates.values())
    names = (
        "catalogue-plan.json",
        "catalogue-inputs.json",
        "catalogue-pairs.jsonl.gz",
        "catalogue-scores.json",
    )
    save_json(OUTPUT / names[1], [source for _, source in records])
    write(OUTPUT / names[2], gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    save_json(
        OUTPUT / names[3],
        dict(
            by_date=dates,
            pooled=pooled,
            pooled_rms_reduction=pooled_reduction,
            dates_improved=gains,
            useful_signed_prior=pooled_reduction >= 0.05 and gains >= 4,
            wall_s=perf_counter() - began,
        ),
    )
    save_json(
        OUTPUT / "catalogue-lock.json",
        dict(files={name: digest((OUTPUT / name).read_bytes()) for name in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    run(parser.parse_args().store)
