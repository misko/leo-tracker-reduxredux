"""Custodian-only creation of the exact and deliberately reduced-model packets."""

import gzip
import json
import secrets

import numpy as np

from ..__main__ import encoded
from . import cold_scenes as base
from . import fresh_scenes

COHORTS = ("exact", "perturbed")
PHASE_SIGMA_S = 0.9
PHASE_LIMIT_S = 3.0
LANE_SIGMA_HZ = 75.0
LANE_LIMIT_HZ = 225.0
LANE_CORRELATION_S = 4.0
EPOCH_SIGMA_SAMPLES = 0.45
EPOCH_LIMIT_SAMPLES = 1.35
GAP_S = (4.0, 8.0)
GAP_PROBABILITY = 0.5


class RetimedOrbit:
    """Perturb the satellite trajectory while reception stays at its original epoch."""

    def __init__(self, satellite, shift_s):
        self.satellite = satellite
        self.shift_s = shift_s

    def sgp4_array(self, julian, fraction):
        return self.satellite.sgp4_array(julian, fraction + self.shift_s / 86400)


def _pack_capture(document):
    return gzip.compress(encoded(document) + b"\n", mtime=0)


def _process(times, rng):
    values = np.empty(len(times))
    values[0] = rng.normal(0, LANE_SIGMA_HZ)
    decay = np.exp(-np.diff(times) / LANE_CORRELATION_S)
    innovation = LANE_SIGMA_HZ * np.sqrt(1 - decay**2) * rng.normal(size=len(decay))
    for index, (retained, noise) in enumerate(zip(decay, innovation, strict=True), start=1):
        values[index] = retained * values[index - 1] + noise
    return np.clip(values, -LANE_LIMIT_HZ, LANE_LIMIT_HZ)


def _lane_groups(document, truth):
    groups = {}
    for index, probe in enumerate(document["probes"]):
        local_counter = probe["valid_start_counter"] - document["first_counter"]
        time = (local_counter + base.RATE * base.PROBE_MS / 2000) / truth[
            "sample_clock_rate_hz"
        ] + truth["clock_bias_s"]
        for peak in probe["candidates"]:
            if peak["passed_fractional_margin_gate"]:
                key = (int(time // 50), probe["channel"], probe["receiver_id"])
                groups.setdefault(key, []).append((index, local_counter, time, peak))
    return groups


def _changed_geometry(document, truth, emitter, satellite, shift, counter, times, rf):
    site = base.geodetic_to_ecef_km(*truth["latlon"], 0.0)
    delay, radial_rate = base._signal(satellite, document["anchor_utc_ns"], times, site)
    changed_delay, changed_rate = base._signal(
        RetimedOrbit(satellite, shift), document["anchor_utc_ns"], times, site
    )
    frame_arguments = (
        emitter["frame_phase_s"],
        truth["clock_bias_s"],
        truth["sample_clock_rate_hz"],
        counter,
        times,
    )
    code = base._relative_epoch(delay, *frame_arguments)
    corrected_code = base._relative_epoch(changed_delay, *frame_arguments)
    return -rf / base.LIGHT_KM_S * (changed_rate - radial_rate), corrected_code - code


def _perturb(document, truth, satellites, rng):
    emitters = {(r["block"], r["channel"]): r for r in truth["emitters"]}
    phase = {
        key: float(np.clip(rng.normal(0, PHASE_SIGMA_S), -PHASE_LIMIT_S, PHASE_LIMIT_S))
        for key in emitters
    }
    period = base.RATE / base.FRAME_HZ
    data = document["probes"]
    lane_audit = []
    for (block, channel, rx), rows in _lane_groups(document, truth).items():
        times = np.asarray([row[2] for row in rows])
        counter = np.asarray([row[1] for row in rows])
        key = block, channel
        emitter = emitters[key]
        df, dt = _changed_geometry(
            document,
            truth,
            emitter,
            satellites[emitter["norad"]],
            phase[key],
            counter,
            times,
            base.CHANNELS[channel - 1],
        )
        oscillator = _process(times, rng)
        epoch_jitter = np.clip(
            rng.normal(0, EPOCH_SIGMA_SAMPLES, len(times)),
            -EPOCH_LIMIT_SAMPLES,
            EPOCH_LIMIT_SAMPLES,
        )
        gap = None
        if rng.random() < GAP_PROBABILITY and times[-1] - times[0] > GAP_S[1]:
            width = float(rng.uniform(*GAP_S))
            start = float(rng.uniform(times[0], times[-1] - width))
            gap = (start, start + width)
        dropped = 0
        for i, (index, _, time, peak) in enumerate(rows):
            if gap is not None and gap[0] <= time < gap[1]:
                data[index]["candidates"] = []
                dropped += 1
                continue
            epoch = peak["integer_epoch_sample"] + peak["fractional_epoch_offset_samples"]
            new_epoch = (epoch + dt[i] + epoch_jitter[i]) % period
            integer = round(float(new_epoch))
            peak["fractional_tracking_cfo_hz"] = float(
                base._wrap_cfo(peak["fractional_tracking_cfo_hz"] + df[i] + oscillator[i])
            )
            peak["integer_epoch_sample"] = integer
            peak["fractional_epoch_offset_samples"] = float(new_epoch) - integer
        lane_audit.append(
            dict(
                block=block,
                channel=channel,
                receiver_id=rx,
                count=len(rows),
                missed=dropped,
                gap_s=gap,
                rms_oscillator_hz=float(np.sqrt(np.mean(oscillator**2))),
                rms_epoch_jitter_samples=float(np.sqrt(np.mean(epoch_jitter**2))),
            )
        )
    return {
        "phase": [
            dict(
                block=block, channel=channel, norad=emitters[block, channel]["norad"], seconds=shift
            )
            for (block, channel), shift in phase.items()
        ],
        "lanes": lane_audit,
    }


def generate(folder, cohort):
    folder.mkdir(mode=0o700)
    source = folder / "generator"
    base.generate(source)
    raw = source / "public"
    initial = base._read(raw / "manifest.json")
    private = source / "private"
    truth = base._read(private / "truth.json")
    catalogue = (raw / "orbit.tle").read_bytes()
    public = folder / "public"
    public.mkdir()
    base._new(public / "orbit.tle", catalogue)
    seeds = {"capture": base._sha((private / "seed.bin").read_bytes())}
    audit = {}
    perturbed = {}
    if cohort == "perturbed":
        seed = secrets.token_bytes(32)
        base._new(private / "perturbation-seed.bin", seed)
        seeds["perturbation"] = base._sha(seed)
        rng = np.random.default_rng(int.from_bytes(seed, "big"))
        first_case = initial["order"][0]
        for case in initial["order"]:
            document = json.loads(gzip.decompress((raw / f"{case}.json.gz").read_bytes()))
            label = truth[case]
            if label["latlon"] is not None:
                satellites = base._constellation(catalogue, document["cutoff_utc_ns"])
                audit[case] = _perturb(
                    document, label, {sat.satnum: sat for sat in satellites}, rng
                )
            else:
                document["probes"] = base._shuffled(perturbed[first_case]["probes"], rng)
            perturbed[case] = document
    elif cohort != "exact":
        raise ValueError("unknown synthetic cohort")
    cases = {}
    for case in initial["order"]:
        supplied = (raw / f"{case}.json.gz").read_bytes()
        if cohort == "perturbed":
            supplied = _pack_capture(perturbed[case])
        base._new(public / f"{case}.json.gz", supplied)
        cases[case] = base._sha(supplied)
    manifest = public / "manifest.json"
    fresh_scenes._new(manifest, dict(cases=cases, order=initial["order"]))
    offer_seed = secrets.token_bytes(32)
    base._new(private / "offer-seed.bin", offer_seed)
    seeds["offer"] = base._sha(offer_seed)
    rng = np.random.default_rng(int.from_bytes(offer_seed, "big"))
    queries, targets = fresh_scenes._offers(initial["order"], truth, rng)
    offers = public / "offers.json"
    labels = private / "offer-labels.json"
    perturbations = private / "perturbations.json"
    for path, obj in ((offers, queries), (labels, targets), (perturbations, audit)):
        fresh_scenes._new(path, obj)
    fresh_scenes._new(
        folder / "cohort-lock.json",
        dict(
            manifest_sha256=fresh_scenes._sha(manifest),
            catalogue_sha256=base._sha(catalogue),
            offers_sha256=fresh_scenes._sha(offers),
            labels_sha256=fresh_scenes._sha(labels),
            perturbations_sha256=fresh_scenes._sha(perturbations),
            seeds_sha256=seeds,
            generator_input_lock_sha256=fresh_scenes._sha(source / "input-lock.json"),
        ),
    )
