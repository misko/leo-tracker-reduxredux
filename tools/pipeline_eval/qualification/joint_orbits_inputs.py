"""Bind measured archives and generate geographically held synthetic Doppler inputs."""

import gzip
from dataclasses import fields
from hashlib import sha256

import numpy as np

from .. import corpus
from ..__main__ import encoded
from . import cold_scenes as cold
from . import fresh_scenes as offers
from . import lean_support_trial as support
from . import robust_orbit_fit_trials as prior
from . import site_transfer_samples as disturbance
from .cold_input import NativeCapture
from .full_v5_check import _load_case
from .robust_em_trials import load

CONFIRMATION = ("DS26-0261", "DS26-0259", "DS26-0162", "DS26-0060")
PHYSICAL = ("timing", "confirmation", "archive-omitted", "archive-shuffle")
SYNTHETIC = ("synthetic-present", "synthetic-omitted", "synthetic-shuffle")
WRONG_CASE = "DS26-0036"


def archive_cases():
    ids = set(corpus._selection("ds26-common127")[0])
    excluded = set(corpus._selection("roof16")[0]) | set(prior.CONFIRMATION) | set(support.ROOF)
    eligible = []
    for case in ids - excluded:
        record = _load_case(case)
        if all(record.get(k) for k in ("graph", "catalog", "native", "request")):
            eligible.append(case)
    actual = tuple(
        sorted(
            eligible,
            key=lambda case: sha256(("joint-orbits/fresh-archive/v1:" + case).encode()).digest(),
        )[:4]
    )
    if actual != CONFIRMATION:
        raise ValueError("confirmation roster changed")
    return prior.TIMING_IDS + actual


def _row(case, cohort, packet, bindings):
    identifier = case if cohort in PHYSICAL[:2] else f"{case}-{cohort}"
    return dict(id=identifier, recording=case, cohort=cohort, **bindings, packet=packet)


def archive_packets(cache):
    for case in archive_cases():
        packet, bindings = load(case, "matched-tile", cache)
        cohort = "confirmation" if case in CONFIRMATION else "timing"
        yield _row(case, cohort, packet, bindings)
        if case != WRONG_CASE:
            continue
        wrong, verified = load(case, "wrong-region", cache)
        yield _row(case, "archive-omitted", wrong, verified)
        rng = np.random.default_rng(186241)
        shuffled = packet["observation"] | {
            "tracks": [
                track | {"values": rng.permutation(track["values"]).tolist()}
                for track in packet["observation"]["tracks"]
            ]
        }
        yield _row(
            case,
            "archive-shuffle",
            packet | {"observation": shuffled},
            bindings | {"observation_sha256": cold._sha(encoded(shuffled))},
        )


def _synthetic(document, catalogue, tile, cohort):
    raw = gzip.compress(encoded(document) + b"\n", mtime=0)
    capture = NativeCapture(
        **{
            f.name: document[f.name]
            for f in fields(NativeCapture)
            if f.name not in ("catalog", "native_sha256", "catalog_sha256")
        },
        native_sha256=cold._sha(raw),
        catalog_sha256=cold._sha(catalogue),
        catalog=catalogue,
    )
    observation = disturbance.projection(capture)
    return dict(
        id=tile["id"],
        recording=document["case_id"],
        cohort=cohort,
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        observation_sha256=cold._sha(encoded(observation)),
        packet=dict(observation=observation, catalogue=catalogue.decode("ascii"), offer=tile),
    )


def synthetic_packets(seed):
    catalogue, received = disturbance._catalogue()
    pool, _ = disturbance.donors()
    satellites = cold._constellation(catalogue, received)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    labels, realized, rows = {}, {}, []
    first = None
    for i, center in enumerate(((2, -55), (-32, 24))):
        position = np.asarray(center) + rng.uniform(-3, 3, size=2)
        anchor = received + (3600 + i * 360) * cold.NS
        probes, counter, _ = cold._generate_capture(satellites, anchor, position, rng)
        document = dict(
            case_id=rng.bytes(12).hex(),
            probes=probes,
            sample_rate_hz=cold.RATE,
            probe_ms=cold.PROBE_MS,
            first_counter=counter,
            anchor_utc_ns=anchor,
            cutoff_utc_ns=anchor,
            catalog_timestamp_ns=received,
            duration_s=cold.SECONDS,
        )
        realized[document["case_id"]] = disturbance._inject(document, pool, rng)
        for cohort, interval in zip(SYNTHETIC[:2], ((8, 10), (35, 65)), strict=True):
            identifier = rng.bytes(12).hex()
            tile = dict(
                id=identifier,
                width_km=25.0,
                center=offers._destination(
                    position,
                    rng.uniform(*interval),
                    rng.uniform(0, 2 * np.pi),
                ),
            )
            if first is None:
                first = document, tile
            rows.append(_synthetic(document, catalogue, tile, cohort))
            labels[identifier] = position.tolist()
    original, tile = first
    shuffled = original | {
        "case_id": rng.bytes(12).hex(),
        "probes": cold._shuffled(original["probes"], rng),
    }
    identifier = rng.bytes(12).hex()
    rows.append(_synthetic(shuffled, catalogue, tile | {"id": identifier}, SYNTHETIC[2]))
    labels[identifier] = None
    rng.shuffle(rows)
    return rows, labels, realized
