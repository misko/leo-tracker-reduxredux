"""Select digest-bound causal predecessors and no later catalogue records."""

import re
from hashlib import sha256
from pathlib import Path

from sgp4.alpha5 import from_alpha5

from ..variants import phase_forecast as method

PAIRS = re.compile(rb"(?m)^(1 ([A-Z0-9 ]{5})[^\r\n]*)\r?\n(2 \2[^\r\n]*)")


def available(entry):
    raw = Path(entry["path"]).read_bytes()
    if sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError("historical TLE digest mismatch")
    return raw


def satellites(raw, wanted=None):
    for match in PAIRS.finditer(raw):
        number = from_alpha5(match[2].decode("ascii"))
        if wanted is None or number in wanted:
            yield (
                number,
                method.as_satellite(match[1], match[3]),
                sha256(match[1] + b"\n" + match[3] + b"\n").hexdigest(),
            )


def predecessors(current, document, entries, detail):
    cutoff, limit = (document[k] for k in ("cutoff_utc_ns", "catalog_timestamp_ns"))
    oldest = cutoff - method.MAX_HOURS * method.HOUR
    epochs = {sat.satnum: method.epoch_ns(sat) for sat in current}
    order = [entry["collection_ns"] for entry in entries]
    if order != sorted(set(order), reverse=True) or any(not oldest <= s < limit for s in order):
        raise ValueError("unauthorized causal predecessor time or order")
    selected, hashes, consumed = {}, set(), []
    for entry in entries:
        ts = entry["collection_ns"]
        if entry["sha256"] in hashes:
            continue
        hashes.add(entry["sha256"])
        raw = available(entry)
        consumed.append(dict(collection_ns=ts, sha256=entry["sha256"], bytes=len(raw)))
        for number, sat, digest in satellites(raw, epochs):
            epoch = method.epoch_ns(sat)
            if not oldest <= epoch <= min(ts, epochs[number] - method.SECOND):
                continue
            if number not in selected or epoch > selected[number][1]:
                selected[number] = (sat, epoch, ts, digest)
    detail.update(
        history_sources=consumed,
        history_bytes=sum(r["bytes"] for r in consumed),
        historical_pairs=len(selected),
    )
    return selected
