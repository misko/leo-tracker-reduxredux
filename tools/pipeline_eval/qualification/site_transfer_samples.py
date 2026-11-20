"""Draw new native GLRT packets with archive-derived CFO and track support."""

import gzip
import json
import secrets
from collections import defaultdict
from datetime import datetime

import numpy as np

from ..__main__ import encoded
from ..scoring import distance_km
from . import cold_scenes as cold
from .fresh_scenes import _destination, _new, _read, _sha
from .full_v5_check import _load_case

ROOT = cold.REPO
ARCHIVE = ROOT / "reports/2026_11_19_receiver_convergence/track-fit"
TRACE = ARCHIVE / "ownership-trace.jsonl.gz"
AUDIT = ARCHIVE / "ownership-audit.json"
OLD_LABELS = (
    ROOT / "reports/2026_11_19_glrt_cold_start/scenes/scores.json",
    ROOT / "reports/2026_11_19_short_receiver/fresh-scenes/scores.json",
    ROOT / "reports/2026_11_19_receiver_convergence/fresh-transfer/labels-exact.json",
    ROOT / "reports/2026_11_19_receiver_convergence/fresh-transfer/labels-perturbed.json",
)
DONOR_CASES = ("DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247")
BOXES = ((33, -112), (40, -8), (12, 105), (-34, -56))
CONDITIONS = ("present", "missing-near", "missing-far", "shuffle")
INTERVALS = ((8.0, 10.0), (20.0, 28.0), (55.0, 105.0))
WINDOW_S = 40.0


def donors():
    """Validate the previous owner's joined records against their frozen authority."""
    archive = _read(AUDIT)
    with gzip.open(TRACE, "rt") as stream:
        groups = list(map(json.loads, stream))
    if tuple(g["case"] for g in groups) != DONOR_CASES:
        raise ValueError("the donor capture roster changed")
    if [{k: v for k, v in g.items() if k != "rows"} for g in groups] != archive:
        raise ValueError("the donor traces and archive audit disagree")
    pool, receipts = [], []
    for group in groups:
        case = group["case"]
        record = _load_case(case)
        binding = group["bindings"]
        if (
            binding["native_sha256"] != record["native"]["sha256"]
            or binding["catalog_sha256"] != record["catalog"]["sha256"]
            or binding["observation_sha256"] != record["observation"]
        ):
            raise ValueError("donor provenance does not match the frozen measurement inventory")
        matched = [r for r in group["rows"] if r["agrees"] is True]
        if len(matched) != group["audit"]["same"]["points"]:
            raise ValueError("donor trace agreement count changed")
        reported = group["audit"]["same"]["exact_residual_rms_hz"]
        if not np.isclose(
            np.sqrt(np.mean([r["exact_residual_hz"] ** 2 for r in matched])), reported
        ):
            raise ValueError("donor trace residual statistics changed")
        lanes = defaultdict(list)
        for row in matched:
            key = row["receiver"], row["channel"], row["track"], row["norad"]
            lanes[key].append((row["time_s"], row["exact_residual_hz"]))
        n = len(pool)
        for (rx, channel, track, _), pairs in sorted(lanes.items()):
            t, f = np.asarray(sorted(pairs)).T
            if len(t) >= 24 and np.ptp(t) >= 44 and (np.diff(t) > 0).all():
                pool.append((dict(case=case, receiver=rx, channel=channel, track=track), t, f))
        receipts.append(
            dict(
                case=case,
                bindings=binding,
                matched_rows=len(matched),
                qualified_tracks=len(pool) - n,
                input_sha256=group["input_sha256"],
                v5_receipt_sha256=group["v5_receipt_sha256"],
            )
        )
    if not pool:
        raise ValueError("no valid empirical residual templates")
    return pool, receipts


def _window(pool, rng):
    key, times, cfo = pool[int(rng.integers(len(pool)))]
    start = rng.uniform(times[0], times[-1] - WINDOW_S)
    selected = (times >= start) & (times < start + WINDOW_S)
    offsets = times[selected] - start
    values = cfo[selected]
    return key | {"window_start_s": float(start)}, offsets, values - np.median(values)


def _inject(document, pool, rng):
    """Replay donor visits at their relative times onto the nearest native probe slots."""
    lanes = defaultdict(list)
    for probe in document["probes"]:
        time = (probe["valid_start_counter"] - document["first_counter"]) / cold.RATE
        time += cold.PROBE_MS / 2000
        kept = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        if kept:
            key = int(time // 50), probe["receiver_id"], probe["channel"]
            lanes[key].append((time, probe, kept[0]))
    receipt = []
    for (block, receiver, channel), rows in sorted(lanes.items()):
        key, offsets, values = _window(pool, rng)
        times = np.array([r[0] for r in rows])
        replay = {}
        for offset, residual in zip(offsets, values, strict=True):
            planned = block * 50 + 5 + offset
            i = int(np.argmin(abs(times - planned)))
            delta = abs(times[i] - planned)
            if delta <= 0.100 and (i not in replay or delta < replay[i][0]):
                replay[i] = delta, residual
        for i, (_, probe, peak) in enumerate(rows):
            if i in replay:
                peak["fractional_tracking_cfo_hz"] = float(
                    cold._wrap_cfo(peak["fractional_tracking_cfo_hz"] + replay[i][1])
                )
            else:
                probe["candidates"] = [r for r in probe["candidates"] if r is not peak]
        kept_times = times[sorted(replay)]
        receipt.append(
            dict(
                donor=key,
                block=block,
                receiver=receiver,
                channel=channel,
                original=len(rows),
                donor_points=len(offsets),
                retained=len(replay),
                retained_span_s=float(np.ptp(kept_times)) if len(kept_times) else 0.0,
                retained_max_gap_s=float(np.max(np.diff(kept_times)))
                if len(kept_times) > 1
                else 0.0,
                residual_rms_hz=float(np.sqrt(np.mean(values**2))),
                residual_lag1=float(np.corrcoef(values[:-1], values[1:])[0, 1])
                if len(values) > 2 and min(np.std(values[:-1]), np.std(values[1:])) > 0
                else None,
                median_source_interval_s=float(np.median(np.diff(offsets)))
                if len(offsets) > 1
                else None,
            )
        )
    return receipt


def projection(capture):
    """Group time-contiguous folded CFO hypotheses without any orbital information."""
    lanes = defaultdict(list)
    for probe in capture.probes:
        key = probe["receiver_id"], probe["channel"], probe["actual_rf_hz"]
        time = (probe["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
        time += probe["probe_start_ms"] / 1000 + capture.probe_ms / 2000
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        if eligible:
            best = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
            lanes[key].append((time, best["fractional_tracking_cfo_hz"]))
    tracks = []
    for (rx, ch, rf), lane in sorted(lanes.items()):
        fragments = [[]]
        for t, f in sorted(lane):
            segment = fragments[-1]
            if segment:
                previous_t, previous_f = segment[-1]
                dt = t - previous_t
                increment = cold._wrap_cfo(f - previous_f)
                if 0 < dt <= 8.0 and abs(increment) <= 6500 * dt:
                    f = float(previous_f + increment)
                else:
                    fragments.append([])
            fragments[-1].append((t, f))
        for segment in fragments:
            if len(segment) < 8 or segment[-1][0] - segment[0][0] < 12.0:
                continue
            times, values = zip(*segment, strict=True)
            tracks.append(dict(times=times, values=values, receiver=rx + 1, channel=ch, rf_hz=rf))
    return {
        key: getattr(capture, key)
        for key in ("anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s")
    } | dict(tracks=tracks)


def _catalogue():
    snapshot = _read(cold.SNAPSHOT)
    received = cold._stamp(datetime.fromisoformat(snapshot["retrieved_at"]))
    catalogue = (cold.TLE_ARCHIVE / snapshot["raw_object"]).read_bytes()
    if (
        cold._sha(catalogue) != snapshot["raw_sha256"]
        or cold._sha(catalogue) != cold.CATALOG_SHA256
        or cold._stamp(datetime.fromisoformat(snapshot["tle_epoch_max"])) > received
    ):
        raise ValueError("the generator's causal TLE is unavailable")
    return catalogue, received


def _offers(order, labels, rng):
    offers, targets = [], {}
    first_tile = None
    for capture_id in order:
        truth = labels[capture_id]
        roles = CONDITIONS[:3] if truth is not None else ("shuffle",)
        for i, role in enumerate(roles):
            identifier = rng.bytes(12).hex()
            if truth is None:
                tile = first_tile | {"id": identifier}
            else:
                center = _destination(truth, rng.uniform(*INTERVALS[i]), rng.uniform(0, 2 * np.pi))
                tile = dict(id=identifier, center=center, width_km=25.0)
                if first_tile is None:
                    first_tile = tile
            offers.append(dict(id=identifier, capture_id=capture_id, tile=tile))
            targets[identifier] = dict(condition=role, capture_id=capture_id, latlon=truth)
    rng.shuffle(offers)
    return offers, targets


def generate(root):
    public, private = root / "public", root / "private"
    public.mkdir()
    private.mkdir(mode=0o700)
    pool, receipts = donors()
    _new(
        root / "donor-receipt.json",
        dict(trace_sha256=_sha(TRACE), audit_sha256=_sha(AUDIT), cases=receipts),
    )
    catalogue, received = _catalogue()
    cold._new(public / "orbit.tle", catalogue)
    rngs = []
    for key in ("capture", "disturbance", "offer"):
        raw = secrets.token_bytes(32)
        cold._new(private / f"seed-{key}.bin", raw)
        rngs.append(np.random.default_rng(int.from_bytes(raw, "big")))
    geometries, disturbances, offer_rng = rngs
    previous = set()
    for path in OLD_LABELS:
        rows = _read(path)
        rows = rows.get("generated_truth", rows.get("labels", rows))
        for row in rows.values():
            if row.get("latlon") is not None:
                previous.add(tuple(row["latlon"]))
    sats = cold._constellation(catalogue, received)
    manifest, labels, audit = {}, {}, {}

    def publish(doc, label):
        case = doc["case_id"]
        raw = gzip.compress(encoded(doc) + b"\n", mtime=0)
        cold._new(public / f"{case}.json.gz", raw)
        labels[case] = label
        manifest[case] = cold._sha(raw)

    first = None
    for i, center in enumerate(BOXES):
        site = tuple(map(float, np.asarray(center) + geometries.uniform(-3, 3, size=2)))
        if any(distance_km(site, old) < 600 for old in previous):
            raise ValueError("new site overlaps an earlier synthetic geography")
        anchor = received + (1800 + i * 360) * cold.NS
        probes, counter, _ = cold._generate_capture(sats, anchor, site, geometries)
        document = dict(
            case_id=geometries.bytes(12).hex(),
            probes=probes,
            sample_rate_hz=cold.RATE,
            probe_ms=cold.PROBE_MS,
            first_counter=counter,
            anchor_utc_ns=anchor,
            cutoff_utc_ns=anchor,
            catalog_timestamp_ns=received,
            duration_s=cold.SECONDS,
        )
        audit[document["case_id"]] = _inject(document, pool, disturbances)
        publish(document, site)
        if first is None:
            first = document
    shuffled = first | {
        "case_id": geometries.bytes(12).hex(),
        "probes": cold._shuffled(first["probes"], disturbances),
    }
    publish(shuffled, None)
    order = list(manifest)
    offers, targets = _offers(order, labels, offer_rng)
    _new(public / "manifest.json", dict(cases=manifest, order=order))
    _new(public / "offers.json", offers)
    _new(private / "labels.json", targets)
    _new(private / "realized-disturbances.json", audit)
