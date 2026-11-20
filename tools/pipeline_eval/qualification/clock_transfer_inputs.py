"""Custodian generation of independent, realistic GLRT-factor transfer scenes."""

from datetime import datetime

import numpy as np
from scipy.optimize import brentq

from leo.sky.propagation import parse_element_sets

from ..__main__ import encoded
from ..scoring import distance_km
from . import cold_scenes as cold
from . import site_transfer_samples as empirical
from .fresh_scenes import _destination, _new, _read, _sha
from .native_joint_full_results import roi_margin

ROOT = cold.REPO
BOXES = ((48, -119), (25, 30), (-27, 153), (35, 138), (-29, -70), (7, -2))
KINDS = ("original", "near-inside", "near-outside", "far-outside", "shuffle")
TLE_DAYS = ("15", "16", "17", "18")
PAST = empirical.OLD_LABELS + (
    ROOT / "reports/2026_11_19_receiver_screening/site-transfer/labels.json",
    ROOT / "reports/2026_11_19_receiver_screening/inference/joint-orbits/scores.json",
)


def snapshots():
    root = cold.TLE_ARCHIVE / "snapshots/space-track/starlink/2026/11"
    rows = []
    for day in TLE_DAYS:
        for path in (root / day).glob("*.json"):
            data = _read(path)
            received = cold._stamp(datetime.fromisoformat(data["retrieved_at"]))
            epoch = cold._stamp(datetime.fromisoformat(data["tle_epoch_max"]))
            if epoch <= received:
                rows.append(
                    dict(
                        path=str(path.relative_to(cold.TLE_ARCHIVE)),
                        received=received,
                        sha256=data["raw_sha256"],
                        metadata_sha256=_sha(path),
                        raw_object=data["raw_object"],
                    )
                )
    result = sorted(rows, key=lambda r: r["received"])
    if len(result) < 30:
        raise ValueError("insufficient authentic TLE histories for independent draws")
    return result


def _history(rows, used, rng):
    choices = []
    for i, first in enumerate(rows[:-1]):
        if first["sha256"] in used:
            continue
        later = [
            row
            for row in rows[i + 1 :]
            if row["sha256"] not in used | {first["sha256"]}
            and 2 * 3600 * cold.NS <= row["received"] - first["received"] <= 6 * 3600 * cold.NS
        ]
        if later and rows[i + 1]["received"] - first["received"] >= 90 * 60 * cold.NS:
            choices.append((first, later))
    earlier, eligible = choices[int(rng.integers(len(choices)))]
    later = eligible[int(rng.integers(len(eligible)))]
    at = earlier["received"] + int(rng.uniform(10, 90) * 60 * cold.NS)
    return earlier, later, at


def _tle(record):
    path = cold.TLE_ARCHIVE / record["raw_object"]
    raw = path.read_bytes()
    if cold._sha(raw) != record["sha256"]:
        raise ValueError("authentic catalogue object differs from its bound digest")
    return raw


def _true_bank(causal, revised, at, revisited):
    first = parse_element_sets(causal.decode("ascii"))
    members = {
        sat.satnum
        for sat, epoch in zip(first.satellites, first.element_epoch_utc_ns(), strict=True)
        if at - 48 * 3600 * cold.NS <= epoch <= at
    }
    return [sat for sat in cold._constellation(revised, revisited) if sat.satnum in members]


def _prior_sites():
    previous = set()
    for path in PAST:
        data = _read(path)
        labels = data.get("generated_truth", data.get("labels", data))
        previous.update(tuple(r["latlon"]) for r in labels.values() if r.get("latlon") is not None)
    return previous


def _tile(identifier, center):
    return dict(id=identifier, center=center, width_km=25.0)


def _at_margin(identifier, site, bearing, signed):
    def trial(km):
        return _tile(identifier, _destination(site, km, bearing))

    distance = brentq(lambda km: roi_margin(site, trial(km)) - signed, 0, 200, xtol=1e-8)
    return trial(distance)


def _offers(site, rng):
    near = rng.uniform(1.0, 2.0)
    bearing = rng.uniform(0, 2 * np.pi)
    centers = [
        _tile(
            rng.bytes(12).hex(), _destination(site, rng.uniform(8, 10), rng.uniform(0, 2 * np.pi))
        ),
        _at_margin(rng.bytes(12).hex(), site, bearing, near),
        _at_margin(rng.bytes(12).hex(), site, bearing, -near),
        _at_margin(rng.bytes(12).hex(), site, rng.uniform(0, 2 * np.pi), -rng.uniform(35, 65)),
    ]
    return list(zip(KINDS[:-1], centers, strict=True))


def _native(case, anchor, first, probes):
    clock = {"realtime_ns": anchor}
    return dict(
        clock_anchor=dict(before=clock, after=clock, sample_counter=first),
        last_sample_counter=first + cold.RATE * cold.SECONDS,
        source=dict(
            probe_ms=cold.PROBE_MS, probes=probes, sample_rate_hz=cold.RATE, session_id=case
        ),
    )


def generate(root, pool, seed, selector, track_config):
    public, private = root / "public", root / "private"
    public.mkdir()
    private.mkdir(mode=0o700)
    cold._new(private / "seed.bin", seed)
    geometry, radio, offers = [
        np.random.default_rng(s)
        for s in np.random.SeedSequence(int.from_bytes(seed, "big")).spawn(3)
    ]
    previous, used, rows, truth, draws, native_hashes = _prior_sites(), set(), [], {}, {}, set()
    graph = public / "track-config.json"
    cold._new(graph, track_config)
    first_capture = first_offer = None

    def bind(case, raw, anchor, received, earlier, tile):
        native = public / f"{case}.json"
        catalogue = public / f"{earlier['sha256']}.tle"
        for path, content in ((native, raw), (catalogue, _tle(earlier))):
            if not path.exists():
                cold._new(path, content)
        digest = cold._sha(raw)
        native_hashes.add(digest)
        return dict(
            id=tile["id"],
            capture_id=case,
            packet=dict(
                mode="native",
                cutoff=anchor,
                catalog_timestamp=received,
                offer=tile,
                probe_limit=2
                * len(np.arange(0, cold.SECONDS * 1000 - cold.PROBE_MS + 1, cold.SLOT_MS)),
                native={"path": "/input/native", "sha256": digest},
                catalogue={"path": "/input/catalogue", "sha256": earlier["sha256"]},
                track_config={"path": "/input/track_config", "sha256": cold._sha(track_config)},
            ),
        )

    for center in BOXES:
        location = tuple(map(float, np.asarray(center) + geometry.uniform(-2, 2, size=2)))
        if any(distance_km(location, old) < 700 for old in previous):
            raise ValueError("new site overlaps an earlier simulated geography")
        for _ in range(8):
            earlier, later, anchor = _history(selector, used, geometry)
            sats = _true_bank(_tle(earlier), _tle(later), anchor, later["received"])
            try:
                probes, counter, physical = cold._generate_capture(sats, anchor, location, radio)
            except ValueError as err:
                if str(err) != "insufficient visible causal orbit opportunities":
                    raise
            else:
                break
        else:
            raise ValueError("eight geometric draws failed the simulator visibility criterion")
        used.update((earlier["sha256"], later["sha256"]))
        case = geometry.bytes(12).hex()
        record = dict(first_counter=counter, probes=probes)
        injection = empirical._inject(record, pool, radio)
        draws[case] = dict(
            trajectory=later,
            causal=earlier,
            capture_utc_ns=anchor,
            emitters=physical["emitters"],
            disturbed_lanes=injection,
        )
        payload = encoded(_native(case, anchor, counter, probes))
        for condition, tile in _offers(location, offers):
            rows.append(bind(case, payload, anchor, earlier["received"], earlier, tile))
            truth[tile["id"]] = dict(
                latlon=location,
                condition=condition,
                capture_id=case,
                margin_km=roi_margin(location, tile),
            )
            if first_capture is None:
                first_capture = earlier, anchor, counter, probes
                first_offer = tile
    earlier, anchor, counter, probes = first_capture
    shuffle = geometry.bytes(12).hex()
    tile = first_offer | {"id": offers.bytes(12).hex()}
    payload = encoded(_native(shuffle, anchor, counter, cold._shuffled(probes, radio)))
    rows.append(bind(shuffle, payload, anchor, earlier["received"], earlier, tile))
    truth[tile["id"]] = dict(latlon=None, condition="shuffle", capture_id=shuffle, margin_km=None)
    if len(native_hashes) != 7 or len(rows) != 25:
        raise ValueError("expected six fresh captures, one shuffle and 25 offers")
    offers.shuffle(rows)
    _new(public / "requests.json", rows)
    _new(private / "truth.json", truth)
    _new(private / "draws.json", draws)
