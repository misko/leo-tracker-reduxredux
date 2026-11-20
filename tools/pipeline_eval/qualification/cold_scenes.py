"""Prospective synthetic GLRT candidates from causal Starlink orbital elements."""

import argparse
import gzip
import hashlib
import importlib
import json
import os
import secrets
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds, validate_result
from .cold_input import CANDIDATE_FIELDS, PROBE_FIELDS, NativeCapture

REPO = Path(__file__).resolve().parents[3]
PROTOCOL = REPO / "reports/2026_11_19_glrt_cold_start/scenes/PROTOCOL.md"
TLE_ARCHIVE = Path("/mnt/qnap01/mouse9911/tle")
SNAPSHOT = TLE_ARCHIVE / (
    "snapshots/space-track/starlink/2026/11/14/20261114T053700Z-5f56298337ea.json"
)
CATALOG_SHA256 = "5f56298337ea6d22fe99064f25c533eabb7de571aad0f5cb2991c59fac858cdd"
METHODS = {"point_votes": "solve", "rate_triplets": "run", "folded_doppler": "solve"}
TITLES = ("Point-pair votes", "Rate triplets", "Folded Doppler")
RELEASES = {
    "point_votes.py": "f8186edc25eccb52556e22855d3fb870037d64c643f956bd606461de71d02fcf",
    "rate_triplets.py": "42612cc63e15011d8ec731d87d1c2b90508150fbb78dc9e66e7e4c1fd38920a8",
    "folded_doppler.py": "1028524006842621faab92877a0b115f7fe09168dd037a8d19d044e8f1481311",
    "folded_doppler.c": "fd33e4b90732f1117014b92040f0002a7206a337d9868a6636537693f9e64990",
}
CPUS = set(range(8, 15)) | {17, 18, 19}
MAX_WORKERS = 7
RATE = 10_000_000
PROBE_MS = 20
SLOT_MS = 24
SECONDS = 300
LIGHT_KM_S = 299_792.458
OMEGA = 7.29211514670698e-5
FRAME_HZ = 750
CFO_ALIAS_HZ = 1 / 4.4e-6
NS = 10**9
CHANNELS = tuple(10.825e9 + i * 250e6 for i in range(8))
SITE_BOXES = ((54, 10), (-38, 147), (16, -99), (-18, 29))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    return json.loads(path.read_bytes())


def _new(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def _stamp(date):
    elapsed = date - datetime(1970, 1, 1, tzinfo=UTC)
    return (elapsed.days * 86400 + elapsed.seconds) * NS + elapsed.microseconds * 1000


def _wrap_cfo(frequency_hz):
    return (frequency_hz + CFO_ALIAS_HZ / 2) % CFO_ALIAS_HZ - CFO_ALIAS_HZ / 2


def _relative_epoch(delay_s, phase_s, clock_offset_s, sample_rate, sample_counter, time_s):
    # An emission at phase + k/750 arrives one light-time later. Choose one
    # representative near the comparison instant and refer it to the probe's counter.
    emission_tick = np.rint((time_s - delay_s - phase_s) * FRAME_HZ)
    arrival_s = emission_tick / FRAME_HZ + phase_s + delay_s
    position = sample_rate * (arrival_s - clock_offset_s) - sample_counter
    return position % (RATE / FRAME_HZ)


def _datum(range_km, ray, satellite_velocity, station_velocity):
    range_rate = np.sum(ray * (satellite_velocity - station_velocity), axis=-1)
    # Differentiate the retarded light-time equation at the reception epoch.
    correction = 1 + np.sum(ray * satellite_velocity, axis=-1) / LIGHT_KM_S
    return range_km / LIGHT_KM_S, range_rate / correction


def _signal(satellite, anchor_ns, time_s, site_ecef):
    julian, fraction = julian_day_from_utc_ns(anchor_ns + np.rint(time_s * NS).astype(np.int64))
    theta = greenwich_mean_sidereal_time_rad(julian, fraction)
    x, y, z = site_ecef
    station = np.column_stack(
        (
            np.cos(theta) * x - np.sin(theta) * y,
            np.sin(theta) * x + np.cos(theta) * y,
            np.full(len(theta), z),
        )
    )
    velocity = OMEGA * np.column_stack((-station[:, 1], station[:, 0], np.zeros(len(station))))
    delay = np.zeros(len(time_s))
    for _ in range(3):
        error, position, satellite_velocity = satellite.sgp4_array(julian, fraction - delay / 86400)
        if error.any():
            raise ValueError("emitter failed SGP4 near reception time")
        delta = position - station
        distance = np.linalg.norm(delta, axis=1)
        delay = distance / LIGHT_KM_S
    return _datum(distance, delta / distance[:, None], satellite_velocity, velocity)


def _constellation(catalog, cutoff):
    parsed = parse_element_sets(catalog.decode("ascii"))
    return [
        sat
        for sat, epoch in zip(parsed.satellites, parsed.element_epoch_utc_ns(), strict=True)
        if epoch <= cutoff
    ]


def _emitters(satellites, anchor, site, frame, rng):
    # Two independent fixed-band transmitters per 50 s interval. Choose from
    # pass opportunities with at least a 25 degree elevation over the full activity.
    samples = np.concatenate(
        [(50 * block) + np.array([3.0, 14.0, 25.0, 36.0, 47.0]) for block in range(6)]
    )
    julian, fraction = julian_day_from_utc_ns(anchor + np.rint(samples * NS).astype(np.int64))
    errors, position, velocity = SatrecArray(satellites).sgp4(julian, fraction)
    position, _ = teme_to_ecef(
        position, velocity, greenwich_mean_sidereal_time_rad(julian, fraction)
    )
    delta = position - site
    radius = np.linalg.norm(position, axis=-1)
    up = (delta @ frame[2]) / np.linalg.norm(delta, axis=-1)
    visible = (
        ((errors == 0) & (up > np.sin(np.deg2rad(25))) & (radius > 6650) & (radius < 7100))
        .reshape(len(satellites), 6, 5)
        .all(axis=-1)
    )
    active = []
    used = set()
    for block in range(6):
        options = [int(i) for i in np.flatnonzero(visible[:, block]) if i not in used]
        if len(options) < 2:
            raise ValueError("insufficient visible causal orbit opportunities")
        selected = [int(i) for i in rng.choice(options, size=2, replace=False)]
        used.update(selected)
        for channel, index in zip((2, 6) if block % 2 else (1, 5), selected, strict=True):
            active.append((block, channel, satellites[index]))
    return active


def _peak(rank, frequency, epoch, margin):
    integer = round(float(epoch))
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=integer,
        fractional_epoch_offset_samples=float(epoch) - integer,
        fractional_tracking_cfo_hz=float(_wrap_cfo(frequency)),
        fractional_exact_score=float(margin) + 0.085,
        fractional_control_score=0.085,
        fractional_margin=float(margin),
        passed_fractional_margin_gate=bool(margin >= 0.025),
    )


def _probe_row(index, rx, channel, start, candidates):
    return dict(
        actual_rf_hz=int(CHANNELS[channel]),
        channel=int(channel + 1),
        edge="lower" if rx == 0 else "upper",
        payload_start_sample=0,
        probe_index=2 * index + rx,
        # valid_start_counter already identifies the first sample in this probe.
        probe_start_ms=0,
        receiver_id=rx,
        valid_start_counter=start,
        visit_index=index,
        candidates=candidates,
    )


def _check_probe_times(probes, first_counter, sample_rate_hz, probe_ms, duration_s):
    for probe in probes:
        start = (probe["valid_start_counter"] - first_counter) / sample_rate_hz
        start += probe["probe_start_ms"] / 1000.0
        if not 0 <= start <= duration_s - probe_ms / 1000.0:
            raise ValueError("synthetic probe timing falls outside its capture")


def _generate_capture(satellites, anchor, site, rng):
    site_ecef = geodetic_to_ecef_km(*site, 0.0)
    frame = ecef_to_enu_matrix(*site)
    emitters = _emitters(satellites, anchor, site_ecef, frame, rng)
    first_counter = int(rng.integers(0, 50_000_000))
    offsets_ms = np.arange(0, SECONDS * 1000 - PROBE_MS + 1, SLOT_MS)
    counter = np.asarray(offsets_ms * RATE // 1000, dtype=np.int64)
    clock_bias_s = float(rng.uniform(-0.004, 0.004))
    clock_rate = RATE * (1 + float(rng.uniform(-0.4e-6, 0.4e-6)))
    sample_time_s = (counter + RATE * PROBE_MS / 2000) / clock_rate + clock_bias_s
    channel_index = np.arange(len(counter)) % len(CHANNELS)
    receiver_lo = rng.uniform(-5000, 5000, size=2)
    receiver_drift = rng.normal(0, 0.8, size=2)
    rf_offset_per_ghz = float(rng.uniform(-3500, 3500))
    geometry = {}
    emitter_truth = []
    for block, channel, sat in emitters:
        chosen = np.flatnonzero(
            (channel_index == channel)
            & (sample_time_s > block * 50 + 3)
            & (sample_time_s < block * 50 + 47)
        )
        delay, radial_rate = _signal(sat, anchor, sample_time_s[chosen], site_ecef)
        offset_hz = float(rng.normal(0, 90))
        phase_s = float(rng.uniform(0, 1 / FRAME_HZ))
        rf = CHANNELS[channel]
        base = -rf / LIGHT_KM_S * radial_rate + offset_hz + rf_offset_per_ghz * (rf / 1e9 - 11.5)
        code = _relative_epoch(
            delay, phase_s, clock_bias_s, clock_rate, counter[chosen], sample_time_s[chosen]
        )
        for index, frequency, epoch in zip(chosen, base, code, strict=True):
            geometry[int(index)] = (float(frequency), float(epoch))
        emitter_truth.append(
            dict(
                block=block,
                channel=channel + 1,
                norad=int(sat.satnum),
                offset_hz=offset_hz,
                frame_phase_s=phase_s,
            )
        )
    probes = []
    for index, (channel, local_counter) in enumerate(zip(channel_index, counter, strict=True)):
        start = int(local_counter + first_counter)
        for rx in range(2):
            candidates = []
            if index in geometry and rng.random() >= 0.03:
                frequency, epoch = geometry[index]
                frequency += receiver_lo[rx] + receiver_drift[rx] * (sample_time_s[index] - 150)
                candidates.append(
                    _peak(
                        1,
                        frequency + rng.normal(0, 24),
                        (epoch + rng.normal(0, 0.12) + 0.4 * rx) % (RATE / FRAME_HZ),
                        rng.uniform(0.26, 0.5),
                    )
                )
            if rng.random() < 0.03:
                candidates.append(
                    _peak(
                        len(candidates) + 1,
                        rng.uniform(-CFO_ALIAS_HZ / 2, CFO_ALIAS_HZ / 2),
                        rng.uniform(0, RATE / FRAME_HZ),
                        rng.uniform(0.008, 0.022),
                    )
                )
            probes.append(_probe_row(index, rx, channel, start, candidates))
    _check_probe_times(probes, first_counter, RATE, PROBE_MS, SECONDS)
    return (
        probes,
        first_counter,
        dict(
            clock_bias_s=clock_bias_s,
            sample_clock_rate_hz=clock_rate,
            lo_hz=receiver_lo.tolist(),
            lo_drift_hz_s=receiver_drift.tolist(),
            rf_constant_hz_per_ghz=rf_offset_per_ghz,
            emitters=emitter_truth,
        ),
    )


def _shuffled(probes, rng):
    # Keep lane, times, occupancy and peak score marginal distributions. Move complete
    # candidate lists between occupied visits, so the lists have no persistent emitter.
    lanes = defaultdict(list)
    for index, probe in enumerate(probes):
        if probe["candidates"]:
            lanes[probe["receiver_id"], probe["channel"]].append(index)
    result = [dict(probe) for probe in probes]
    for indices in lanes.values():
        for lhs, rhs in zip(indices, rng.permutation(indices), strict=True):
            result[lhs]["candidates"] = probes[rhs]["candidates"]
    return result


def _sources():
    names = (
        "tools/pipeline_eval/qualification/cold_scenes.py",
        "tools/pipeline_eval/qualification/cold_input.py",
        "tools/pipeline_eval/scoring.py",
        *(f"tools/pipeline_eval/variants/{filename}" for filename in RELEASES),
        "src/leo/sky/frames.py",
        "src/leo/sky/propagation.py",
    )
    return {name: _sha((REPO / name).read_bytes()) for name in names}


def generate(folder):
    folder.mkdir(mode=0o700)
    public, private = folder / "public", folder / "private"
    public.mkdir()
    private.mkdir(mode=0o700)
    archive_raw = SNAPSHOT.read_bytes()
    archive = json.loads(archive_raw)
    received = _stamp(datetime.fromisoformat(archive["retrieved_at"]))
    catalog = (TLE_ARCHIVE / archive["raw_object"]).read_bytes()
    if _sha(catalog) != archive["raw_sha256"] or _sha(catalog) != CATALOG_SHA256:
        raise ValueError("catalogue differs from the frozen archived object")
    if _stamp(datetime.fromisoformat(archive["tle_epoch_max"])) > received:
        raise ValueError("catalogue has future elements")
    sources = _sources()
    for name, digest in RELEASES.items():
        if sources[f"tools/pipeline_eval/variants/{name}"] != digest:
            raise ValueError(f"solver release changed before synthetic generation: {name}")
    _new(
        folder / "source-lock.json",
        encoded(
            dict(
                sources=sources,
                protocol_sha256=_sha(PROTOCOL.read_bytes()),
                snapshot_sha256=_sha(archive_raw),
                catalog_sha256=CATALOG_SHA256,
            )
        )
        + b"\n",
    )
    _new(public / "orbit.tle", catalog)
    satellites = _constellation(catalog, received)
    seed = secrets.token_bytes(32)
    _new(private / "seed.bin", seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    roster, answers, controls = {}, {}, []
    for index, center in enumerate(SITE_BOXES):
        site = tuple(map(float, np.array(center) + rng.uniform(-5, 5, size=2)))
        case = rng.bytes(12).hex()
        anchor = received + ((index + 1) * 360 + 120) * NS
        probes, counter, truth = _generate_capture(satellites, anchor, site, rng)
        answers[case] = dict(latlon=site, case_index=index, **truth)
        doc = dict(
            case_id=case,
            probes=probes,
            sample_rate_hz=RATE,
            probe_ms=PROBE_MS,
            first_counter=counter,
            anchor_utc_ns=anchor,
            cutoff_utc_ns=anchor,
            catalog_timestamp_ns=received,
            duration_s=SECONDS,
        )
        payload = gzip.compress(encoded(doc) + b"\n", mtime=0)
        _new(public / f"{case}.json.gz", payload)
        roster[case] = _sha(payload)
        if not controls:
            control = rng.bytes(12).hex()
            shuffled = dict(doc, case_id=control, probes=_shuffled(probes, rng))
            payload = gzip.compress(encoded(shuffled) + b"\n", mtime=0)
            _new(public / f"{control}.json.gz", payload)
            roster[control] = _sha(payload)
            controls.append(control)
            answers[control] = dict(latlon=None, case_index=index)
    order = [case for case in roster if case not in controls] + controls
    _new(public / "manifest.json", encoded(dict(cases=roster, order=order)) + b"\n")
    _new(private / "truth.json", encoded(answers) + b"\n")
    _new(
        folder / "input-lock.json",
        encoded(
            dict(
                source_lock_sha256=_sha((folder / "source-lock.json").read_bytes()),
                manifest_sha256=_sha((public / "manifest.json").read_bytes()),
                truth_sha256=_sha((private / "truth.json").read_bytes()),
                seed_sha256=_sha(seed),
            )
        )
        + b"\n",
    )


def _check_lock(folder):
    lock = _read(folder / "input-lock.json")
    source = _read(folder / "source-lock.json")
    if (
        lock["source_lock_sha256"] != _sha((folder / "source-lock.json").read_bytes())
        or lock["manifest_sha256"] != _sha((folder / "public/manifest.json").read_bytes())
        or source["sources"] != _sources()
        or source["protocol_sha256"] != _sha(PROTOCOL.read_bytes())
    ):
        raise ValueError("synthetic input or source differs from its pre-generation seal")
    return lock


def _capture(public, case):
    manifest = _read(public / "manifest.json")
    data = (public / f"{case}.json.gz").read_bytes()
    catalog = (public / "orbit.tle").read_bytes()
    digest = _sha(data)
    document = json.loads(gzip.decompress(data))
    expected = {field.name for field in fields(NativeCapture)} - {
        "catalog",
        "catalog_sha256",
        "native_sha256",
    }
    if (
        set(document) != expected
        or document["case_id"] != case
        or digest != manifest["cases"][case]
        or _sha(catalog) != CATALOG_SHA256
    ):
        raise ValueError("sealed public synthetic input failed validation")
    for probe in document["probes"]:
        if set(probe) != {*PROBE_FIELDS, "candidates"} or any(
            set(p) != set(CANDIDATE_FIELDS) for p in probe["candidates"]
        ):
            raise ValueError("candidate contains a field outside the cold-start contract")
    _check_probe_times(
        document["probes"],
        document["first_counter"],
        document["sample_rate_hz"],
        document["probe_ms"],
        document["duration_s"],
    )
    return NativeCapture(
        **document, catalog=catalog, catalog_sha256=CATALOG_SHA256, native_sha256=digest
    )


def _worker(public, case, method, output):
    capture = _capture(public, case)
    module = importlib.import_module(f"tools.pipeline_eval.variants.{method}")
    started = perf_counter()
    result = getattr(module, METHODS[method])(capture, tile=None)
    elapsed = perf_counter() - started
    validate_result(result)
    save_json(output, dict(id=case, method=method, wall_s=elapsed, result=result))


def _attempt(job):
    public, case, method, target, cpu, timeout = job
    command = [
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-m",
        "tools.pipeline_eval.qualification.cold_scenes",
        "worker",
        str(public),
        case,
        method,
        str(target),
    ]
    started = perf_counter()
    try:
        subprocess.run(command, check=True, timeout=timeout)
        return _read(target)
    except subprocess.TimeoutExpired:
        reason = "fixed synthetic test deadline"
        status = "timed_out"
    except subprocess.CalledProcessError:
        reason = "cold-start solver worker exited unsuccessfully"
        status = "failed"
    return dict(
        id=case,
        method=method,
        wall_s=perf_counter() - started,
        result=dict(status=status, reason=reason, boundary="Global GLRT+Causal TLE", metrics={}),
    )


def _worker_queue(jobs):
    return [_attempt(job) for job in jobs]


def predict(folder, positive_limit, timeout):
    _check_lock(folder)
    public = folder / "public"
    cases = _read(public / "manifest.json")["order"]
    given = [*cases[:-1][:positive_limit], cases[-1]]
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= CPUS or len(cpus) > MAX_WORKERS:
        raise ValueError("Pin at most seven synthetic workers to CPUs 8–14 or 17–19")
    work = folder / "work"
    work.mkdir()
    assignments = [(case, method) for case in given for method in METHODS]
    queues = [
        [
            (public, case, method, work / f"{case}-{method}.json", cpu, timeout)
            for case, method in assignments[index :: len(cpus)]
        ]
        for index, cpu in enumerate(cpus)
    ]
    with ThreadPoolExecutor(len(cpus)) as executor:
        rows = [row for batch in executor.map(_worker_queue, queues) for row in batch]
    _check_lock(folder)
    raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    _new(folder / "predictions.jsonl.gz", raw)
    _new(
        folder / "prediction-lock.json",
        encoded(
            dict(
                mode="global",
                methods=list(METHODS),
                cases=given,
                cpus=cpus,
                per_case_timeout_s=timeout,
                input_lock_sha256=_sha((folder / "input-lock.json").read_bytes()),
                predictions_sha256=_sha(raw),
            )
        )
        + b"\n",
    )


def score(folder, output):
    lock = _check_lock(folder)
    seal = _read(folder / "prediction-lock.json")
    raw = (folder / "predictions.jsonl.gz").read_bytes()
    if seal["input_lock_sha256"] != _sha((folder / "input-lock.json").read_bytes()) or seal[
        "predictions_sha256"
    ] != _sha(raw):
        raise ValueError("synthetic predictions were modified after their seal")
    truth_raw = (folder / "private/truth.json").read_bytes()
    seed = (folder / "private/seed.bin").read_bytes()
    if lock["truth_sha256"] != _sha(truth_raw) or lock["seed_sha256"] != _sha(seed):
        raise ValueError("private synthetic truth differs from the input seal")
    truth = json.loads(truth_raw)
    predictions = list(map(json.loads, gzip.decompress(raw).splitlines()))
    expected = {(case, method) for case in seal["cases"] for method in METHODS}
    if (
        len(predictions) != len(expected)
        or {(r["id"], r["method"]) for r in predictions} != expected
    ):
        raise ValueError("sealed synthetic predictions have missing or duplicate cases")
    rows = []
    for prediction in predictions:
        target = truth[prediction["id"]]["latlon"]
        endpoint = prediction["result"]
        for arm in ARMS:
            a = (endpoint.get("arms") or {}).get(arm, {})
            rows.append(
                dict(
                    id=prediction["id"],
                    method=prediction["method"],
                    arm=arm,
                    control=target is None,
                    wall_s=prediction["wall_s"],
                    status=endpoint["status"],
                    reason=endpoint.get("reason"),
                    latitude_deg=target[0] if target else None,
                    longitude_deg=target[1] if target else None,
                    published=a.get("latlon") is not None,
                    error_km=distance_km(a.get("latlon"), target),
                    forced_error_km=distance_km(a.get("forced_latlon"), target),
                    rf_rms_hz=a.get("rf_rms_hz"),
                    conditional_rms_hz=a.get("conditional_rms_hz"),
                )
            )
    groups = []
    for method in METHODS:
        for arm in ARMS:
            selected = [r for r in rows if r["method"] == method and r["arm"] == arm]
            positives = [r for r in selected if not r["control"]]
            control = [r for r in selected if r["control"]]
            errors = [r["error_km"] for r in positives]
            groups.append(
                dict(
                    method=method,
                    arm=arm,
                    positive_attempts=len(positives),
                    positive_fixes=sum(r["published"] for r in positives),
                    error_km=distribution(errors),
                    within_km=thresholds(errors),
                    negative_attempts=len(control),
                    false_fixes=sum(r["published"] for r in control),
                    forced_error_km=distribution(r["forced_error_km"] for r in positives),
                )
            )
    for name in (
        "source-lock.json",
        "input-lock.json",
        "prediction-lock.json",
        "predictions.jsonl.gz",
    ):
        write(output / name, (folder / name).read_bytes())
    write(output / "seed.hex", seed.hex().encode() + b"\n")
    write(output / "manifest.json", (folder / "public/manifest.json").read_bytes())
    save_json(output / "scores.json", dict(cases=rows, groups=groups, generated_truth=truth))


def figure(scores, output):
    import matplotlib.pyplot as plt

    report = _read(scores)
    rows = report["cases"]
    truth = report["generated_truth"]
    identifiers = sorted(
        {r["id"] for r in rows},
        key=lambda key: (truth[key]["latlon"] is None, truth[key]["case_index"]),
    )
    fig, panels = plt.subplots(1, len(METHODS), figsize=(13, 4.6), sharey=True)
    for ax, method, title in zip(panels, METHODS, TITLES, strict=True):
        positives = [r for r in rows if r["method"] == method and not r["control"]]
        zero, fitted = [sum(r["published"] for r in positives if r["arm"] == arm) for arm in ARMS]
        total = len(positives) // len(ARMS)
        ax.set_title(f"{title}\n{zero}/{total} zero · {fitted}/{total} fitted published")
        for r in (r for r in rows if r["method"] == method):
            x = identifiers.index(r["id"])
            shift = -0.12 if r["arm"] == "c0" else 0.12
            shade = "#146c73" if r["arm"] == "c0" else "#87543f"
            if r["error_km"] is not None:
                ax.scatter(x + shift, max(0.005, r["error_km"]), s=35, color=shade)
            elif r["published"]:
                ax.scatter(x + shift, 0.005, s=35, color="#ba150f", marker="D")
            else:
                ax.scatter(x + shift, 0.004, color=shade, marker="x")
            if r["error_km"] is None and r["forced_error_km"] is not None:
                ax.scatter(
                    x + shift,
                    max(0.005, r["forced_error_km"]),
                    s=35,
                    edgecolors=shade,
                    marker="o",
                    facecolors="none",
                )
        ax.axhline(5, color="#9eaab0", linestyle="--")
        ax.set_yscale("log")
        ax.set_ylim(0.003, 22000)
        ax.set_yticks(
            [0.004, 0.01, 0.1, 1, 5, 100, 1000, 10000],
            ["No fix", "0.01", "0.1", "1", "5", "100", "1,000", "10,000"],
        )
        ax.set_xticks(
            range(len(identifiers)),
            [f"S{i + 1}" for i in range(len(identifiers) - 1)] + ["Shuffle"],
        )
        ax.spines[["top", "right"]].set_visible(False)
    panels[0].set_ylabel("Horizontal error (km)")
    fig.suptitle("Cold-start GLRT candidate control · global search")
    fig.supxlabel("Teal zero calibration · Brown fitted calibration · Open marker forced position")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "predict", "score", "figure", "worker"):
        command = modes.add_parser(name)
        command.add_argument("path", type=Path)
        if name in ("score", "figure"):
            command.add_argument("output", type=Path)
        if name == "predict":
            command.add_argument("--positive-limit", type=int, choices=(2, 3, 4), default=4)
            command.add_argument("--timeout", type=int, default=150)
        if name == "worker":
            command.add_argument("case")
            command.add_argument("method", choices=METHODS)
            command.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "predict":
        predict(args.path, args.positive_limit, args.timeout)
    elif args.command == "worker":
        _worker(args.path, args.case, args.method, args.output)
    elif args.command == "generate":
        generate(args.path)
    else:
        {"score": score, "figure": figure}[args.command](args.path, args.output)


if __name__ == "__main__":
    main()
