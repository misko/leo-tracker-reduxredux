"""Load the most recent usable causal predecessor into a numeric phase-width port."""

import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
from sgp4.alpha5 import from_alpha5
from sgp4.api import Satrec, SatrecArray

from leo.sky.frames import julian_day_from_utc_ns

NS = 1_000_000_000
DAY = 86400 * NS
MAX_AGE_NS = 3 * DAY
TLE = re.compile(rb"(?m)^1 ([A-Z0-9 ]{5})[^\r\n]*\r?\n(2 \1[^\r\n]*)")


def epoch_ns(raw):
    yy, days, decimals = int(raw[:2]), int(raw[2:5]), int(raw[6:14])
    year = (1900 if yy >= 57 else 2000) + yy
    return (
        int(datetime(year, 1, 1, tzinfo=UTC).timestamp()) * NS
        + (days - 1) * DAY
        + decimals * 864000
    )


def widths(satellites, document, bindings, audit):
    start, cpu = perf_counter(), process_time()
    anchor = document["anchor_utc_ns"]
    cutoff = document["cutoff_utc_ns"]
    current_collection = document["catalog_timestamp_ns"]
    if not current_collection <= cutoff <= anchor:
        raise ValueError("catalogue collection and observation clocks are not causal")
    epochs = [round((s.jdsatepoch - 2440587.5 + s.jdsatepochF) * DAY) for s in satellites]
    index = {s.satnum: i for i, s in enumerate(satellites)}
    previous = {}
    if any(epoch > current_collection for epoch in epochs):
        raise ValueError("a current element postdates its catalogue collection")
    sources, seen, previous_sizes = [], set(), []
    order = [r["collection_ns"] for r in bindings]
    if order != sorted(set(order), reverse=True) or any(
        not (cutoff - MAX_AGE_NS <= stamp < current_collection) for stamp in order
    ):
        raise ValueError("phase array contains a future or out-of-window source")
    for entry in bindings:
        collection = entry["collection_ns"]
        if len(previous) == len(satellites) and all(
            row[0] >= collection for row in previous.values()
        ):
            break
        checksum = entry["sha256"]
        if checksum in seen:
            continue
        seen.add(checksum)
        raw = Path(entry["path"]).read_bytes()
        if sha256(raw).hexdigest() != checksum:
            raise ValueError("causal historical file differs from its binding")
        sources.append(dict(sha256=checksum, collection_ns=collection, bytes=len(raw)))
        for match in TLE.finditer(raw):
            number = from_alpha5(match[1].decode("ascii"))
            i = index.get(number)
            if i is None:
                continue
            epoch = epoch_ns(raw[match.start() + 18 : match.start() + 32])
            if cutoff - MAX_AGE_NS <= epoch <= min(collection, epochs[i] - NS) and (
                i not in previous or epoch > previous[i][0]
            ):
                lines = (raw[match.start() : match.start(2)].rstrip(), match[2])
                previous[i] = (epoch, lines, checksum, collection)
    result = np.full(len(satellites), 2.5)
    for _, lines, _, _ in previous.values():
        previous_sizes.append(sum(map(len, lines)) + 2)
    if previous:
        old_idx = sorted(previous)
        old_sat = [
            Satrec.twoline2rv(*(line.decode("ascii") for line in previous[i][1])) for i in old_idx
        ]
        new_sat = [satellites[i] for i in old_idx]
        if any(a.satnum != b.satnum for a, b in zip(old_sat, new_sat, strict=True)):
            raise ValueError("historical identity diverges from the causal tile")
        jd, fr = julian_day_from_utc_ns(np.array([anchor], dtype=np.int64))
        fail_old, r_old, _ = SatrecArray(old_sat).sgp4(jd, fr)
        fail_new, r_new, v_new = SatrecArray(new_sat).sgp4(jd, fr)
        vel = v_new[:, 0]
        speed_square = np.sum(vel**2, axis=1)
        delta = np.sum((r_old[:, 0] - r_new[:, 0]) * vel, axis=1)
        gaps = np.asarray([epochs[i] - previous[i][0] for i in old_idx], dtype=float)
        ages = np.asarray([anchor - epochs[i] for i in old_idx], dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            estimate = np.hypot(1.0, (delta / speed_square) * (ages / gaps))
        valid = (fail_old[:, 0] == 0) & (fail_new[:, 0] == 0) & np.isfinite(estimate)
        result[np.array(old_idx)[valid]] = estimate[valid]
        pairs = int(valid.sum())
    else:
        pairs = 0
    audit.update(
        width_pairs=pairs,
        fallback_orbits=len(satellites) - pairs,
        sgp4_calls=2 * len(previous),
        historical_sources=sources,
        history_bytes=sum(s["bytes"] for s in sources),
        retained_tle_bytes=sum(previous_sizes),
        wall_s=perf_counter() - start,
        cpu_s=process_time() - cpu,
        numeric_port_bytes=result.nbytes,
    )
    return result
