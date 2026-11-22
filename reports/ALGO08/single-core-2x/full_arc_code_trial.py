"""Test held circular pilot code over continuous arcs at two public faces."""

import argparse
import gzip
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.operations.causal_tle_catalogue import causal_catalogue
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from tools.pipeline_eval.qualification import range_epoch_model as code
from tools.pipeline_eval.qualification.range_epoch_trial import native_winners
from tools.pipeline_eval.variants.code_carrier import carrier_samples

from .absolute_timing_trial import PAIRS_SHA256
from .mirrored_orbit_weight_trial import CURVES_SHA256, curves, study

PROBES = (-1., -.5, 0., .25, .5, .75, 1., 1.5, 2.)
RATE_LIMIT_PPM = .35
WAVEFORM_SOURCE_SHA256 = "ae185e1e1216be00932c6f94755183479ac68e274be120524dd617e27cca8447"
SITES = ("north", "south")


def paired_arcs(design, pairing, native, configuration):
    graph = prepare_tracks(native, configuration)
    if graph["metadata"]["anchor_utc_ns"] != design["origin_utc_ns"]:
        raise ValueError("Native timing origin differs from the unlabeled prediction lock")
    index = {}
    for track in graph["tracks"]:
        key = track["receiver"], track["rf_hz"], tuple(track["times"])
        if key in index:
            raise ValueError("Ambiguous source track in pilot phase join")
        index[key] = track
    winners = native_winners(native)
    rows = []
    for locked in design["tracks"]:
        track = index[locked["receiver"], locked["rf"], tuple(locked["times"])]
        support = zip(track["observation_ids"], track["times"], track["values"], strict=True)
        for key, t, f in support:
            row = winners[key]
            if (row["rx"] != track["receiver"] or row["channel"] != track["channel"]
                    or row["rf_hz"] != track["rf_hz"] or abs(row["time_s"] - t) > 1e-9
                    or abs(code.wrap(row["folded_hz"] - f, code.FOLD_HZ)) > 1e-5):
                raise ValueError("Graph row differs from the exact native signal")
            rows.append(dict(row, norad=locked["norad"]))
    period = native["source"]["sample_rate_hz"] / code.FRAME_HZ
    groups = defaultdict(list)
    for left, right in zip(pairing["first"], pairing["second"], strict=True):
        a, b = rows[left], rows[right]
        if ((a["rx"], b["rx"]) != (1, 2)
                or any(a[k] != b[k] for k in ("norad", "time_s", "channel", "rf_hz"))):
            raise ValueError("Frozen pair is not one simultaneous, same-emitter measurement")
        phase = code.wrap(a["phase"] + .5 * code.wrap(b["phase"] - a["phase"], period), period)
        cfo = a["folded_hz"] + .5 * code.wrap(b["folded_hz"] - a["folded_hz"], code.FOLD_HZ)
        groups[a["norad"], a["rf_hz"]].append(
            dict(v5_owner=a["norad"], rf_hz=a["rf_hz"], time_s=a["time_s"],
                 phase=phase, folded_hz=cfo, component=str(a["channel"])),
        )
    arcs = []
    for group in sorted(groups):
        qualifying = list(code.split(sorted(groups[group], key=lambda row: row["time_s"])))
        if qualifying:
            arcs.append(max(qualifying, key=lambda arc: arc.time_s[-1] - arc.time_s[0]))
    return arcs


def bounded_residual(arcs, propagation, rate, *, observations=None):
    """Fit a grouped circular phase and bounded common rate on training rows."""
    period = rate / code.FRAME_HZ
    scale = 2 * np.pi / period
    bound = rate * RATE_LIMIT_PPM * 1e-6
    observed = [arc.phase for arc in arcs] if observations is None else observations
    values = [code.wrap(y - model, period)
              for y, model in zip(observed, propagation, strict=True)]
    times = [arc.time_s - arc.time_s[0] for arc in arcs]
    train = [arc.train for arc in arcs]
    points = [np.exp(scale * 1j * y[keep]) for y, keep in zip(values, train, strict=True)]
    stamps = [scale * t[keep] for t, keep in zip(times, train, strict=True)]

    def resultant(drift):
        return np.array([np.mean(y * np.exp(-1j * drift * t))
                         for y, t in zip(points, stamps, strict=True)])

    def loss(drift):
        return -float(np.mean(np.abs(resultant(drift))))

    grid = np.linspace(-bound, bound, 33)
    best = int(np.argmin([loss(value) for value in grid]))
    interval = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    optimized = minimize_scalar(loss, bounds=interval, method="bounded",
                                 options={"xatol": 1e-10}).x
    drift = float(min([grid[best], optimized], key=loss))
    phase = np.angle(resultant(drift)) / scale
    residual = [code.wrap(y - initial - t * drift, period)
                for y, initial, t in zip(values, phase, times, strict=True)]
    return residual, drift


def held(arcs, residual):
    by_orbit = defaultdict(list)
    for arc, row in zip(arcs, residual, strict=True):
        by_orbit[arc.owner].extend(row[~arc.train] ** 2)
    mse = {int(owner): float(np.mean(values)) for owner, values in by_orbit.items()}
    return dict(orbit_mse=mse, held_rms_samples=float(np.sqrt(np.mean(list(mse.values())))))


def accumulated_carrier(arc, rate):
    cfo = np.r_[arc.cfo[0], arc.cfo[0] + np.cumsum(code.wrap(np.diff(arc.cfo), code.FOLD_HZ))]
    return np.r_[0., np.cumsum(carrier_samples(cfo, np.diff(arc.time_s), arc.rf_hz, rate))]


def evaluate(arcs, delays, rate):
    runs = {}
    for name, model in delays.items():
        residuals, drift = bounded_residual(arcs, model, rate)
        runs[name] = held(arcs, residuals) | {"drift_samples_per_s": drift}
    return runs


def outcome(runs):
    grid = [runs[f"u{u}"]["held_rms_samples"] for u in PROBES]
    a, b = (runs[name]["held_rms_samples"] for name in ("u0.0", "u1.0"))
    return dict(best_u=PROBES[int(np.argmin(grid))], a_rms_samples=a, b_rms_samples=b,
                delta_b_minus_a_samples2=b**2 - a**2)


def geometry(site_spec, pairs, document, configuration, archive):
    arcs = paired_arcs(site_spec, pairs, document, configuration)
    orbit_ids = sorted({arc.owner for arc in arcs})
    if len(orbit_ids) < 2:
        raise ValueError("Too few qualifying satellites for leave-one-out timing")
    rate = document["source"]["sample_rate_hz"]
    cutoff = document["clock_anchor"]["before"]["realtime_ns"]
    causal = causal_catalogue(archive, cutoff)
    snapshots = sorted({r["snapshot_digest"] for r in causal.provenance})
    # Both public earlier panels bind the same past archive. The pin contains
    # no containment outcome and is evaluated before geometry labels are read.
    if snapshots != sorted(SNAPSHOT_PINS):
        raise ValueError("Unexpected capture-causal archive")
    bank = dict(zip(causal.catalogue.satellite_numbers, causal.catalogue.satellites, strict=True))
    a, b = np.asarray(site_spec["faces"])
    positions = {f"u{u}": (a + u * (b - a)).tolist() for u in PROBES}
    delays = {}
    for name, position in positions.items():
        xyz = geodetic_to_ecef_km(*position, 0.)
        delays[name] = [rate * study.cold_scenes._signal(
            bank[arc.owner], site_spec["origin_utc_ns"], arc.time_s, xyz,
        )[0] for arc in arcs]
    delays["negative_A"] = [-row for row in delays["u0.0"]]
    delays["negative_B"] = [-row for row in delays["u1.0"]]
    delays["null"] = [np.zeros(len(arc.time_s)) for arc in arcs]
    return arcs, rate, orbit_ids, snapshots, positions, delays


def arc_summary(arcs):
    return [dict(norad=arc.owner, rf_hz=arc.rf_hz, duration_s=float(np.ptp(arc.time_s)),
                 train=int(arc.train.sum()), held=int((~arc.train).sum())) for arc in arcs]


def infer(site, site_spec, pairs, document, configuration, archive):
    arcs, rate, orbit_ids, snapshots, positions, delays = geometry(
        site_spec, pairs, document, configuration, archive,
    )
    runs = evaluate(arcs, delays, rate)
    loo = {}
    for owner in orbit_ids:
        keep = [index for index, arc in enumerate(arcs) if arc.owner != owner]
        aligned = {name: [rows[index] for index in keep] for name, rows in delays.items()}
        loo[owner] = outcome(evaluate([arcs[index] for index in keep], aligned, rate))
    diagnostic = {}
    for sign in (1., -1.):
        model = [sign * accumulated_carrier(arc, rate) for arc in arcs]
        errors, slopes = code.frame_residual(arcs, model, rate, per_arc=True)
        diagnostic[str(sign)] = held(arcs, errors) | {"slopes_samples_per_s": slopes}
    separation, _ = bounded_residual(arcs, delays["u1.0"], rate, observations=delays["u0.0"])
    return dict(
        site=site, causal_snapshots=snapshots, native_sha256=site_spec["native_sha256"],
        positions=positions, results=runs, outcome=outcome(runs), leave_one_satellite_out=loo,
        carrier=diagnostic, held_geometric_separation=held(arcs, separation),
        arcs=arc_summary(arcs),
    )


SNAPSHOT_PINS = (
    "sha256:1148e4bc038e5bd8a8702c66425261e5a67d11b4b2427818c73fb9308fcb8deb",
    "sha256:1a730e3fc41fb81e9ca09fb7e792b05764b92277a9322b7d0dbdfa6410b29a19",
    "sha256:20475481baa8eb4be510c955483280abd96b5ff0d2bb418aa840184b44b772e3",
    "sha256:36252c1f8ef4ca1fe523c1b9d1a108b6a524eed83ecd625c9f89379294e5dde5",
    "sha256:5f56298337ea6d22fe99064f25c533eabb7de571aad0f5cb2991c59fac858cdd",
)


def predict(native, archive, config, *, model=infer):
    prediction = curves()
    locked = study.inputs.MEASUREMENTS / "mirrored-noise-lock.json.gz"
    raw = gzip.decompress(locked.read_bytes())
    if sha256(raw).hexdigest() != PAIRS_SHA256:
        raise ValueError("The simultaneous phase pairs changed")
    pairs = json.loads(raw)
    generator = Path(__file__).resolve().parents[3] / (
        "tools/pipeline_eval/qualification/waveform_site_model.py"
    )
    if sha256(generator.read_bytes()).hexdigest() != WAVEFORM_SOURCE_SHA256:
        raise ValueError("The audited continuous-transmit-phase generator changed")
    cfg = study.inputs.verified(config, study.arrival.TRACK_CONFIG)["config"]
    results = {}
    for site in SITES:
        design, pairing = prediction["sites"][site], pairs["sites"][site]
        if design["native_sha256"] != pairing["native_sha256"]:
            raise ValueError("Pairing is bound to a different native waveform")
        document = study.inputs.verified(native[site], design["native_sha256"])
        results[site] = model(site, design, pairing, document, TrackConfig(**cfg), archive)
    return dict(causal_curves_sha256=CURVES_SHA256, pairs_sha256=PAIRS_SHA256,
                generator_sha256=WAVEFORM_SOURCE_SHA256, sites=results)


def reveal(prediction, pin):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km

    raw = prediction.read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError("The sealed observations were changed before label reveal")
    known = study.arrival.pinned_packet("region-mirrors.json.gz")["sites"]
    rows = {}
    for site, result in json.loads(raw)["sites"].items():
        offers = known[site]
        if any(row["native_sha256"] != result["native_sha256"] for row in offers.values()):
            raise ValueError("Offer labels belong to a different waveform")
        order = sorted(offers, key=lambda condition: offers[condition]["offer"]["center"])
        known_containing = "AB"[order.index("inside")]

        def classify(u, result=result, offers=offers):
            point = result["positions"][f"u{u}"]
            clearances = {key: face_clearance_km(value["offer"], point)
                          for key, value in offers.items()}
            unresolved = u in (PROBES[0], PROBES[-1])
            return dict(u=u, unresolved=unresolved, clearance_km=clearances,
                        separates=(not unresolved and clearances["inside"] >= -1e-8
                                   and clearances["outside"] < -1e-8))

        first, second = (result["results"][f"u{u}"]["held_rms_samples"] for u in (0., 1.))
        controls = result["results"]
        physically_positive = min(first, second) < min(
            controls[k]["held_rms_samples"] for k in ("null", "negative_A", "negative_B")
        )
        line = classify(result["outcome"]["best_u"])
        loo = {k: classify(value["best_u"])
               for k, value in result["leave_one_satellite_out"].items()}
        rows[site] = dict(
            known_containing_hypothesis=known_containing,
            chosen_face="A" if first < second else "B" if second < first else "tie",
            physically_positive=physically_positive, best_line=line, leave_one_out=loo,
            separates_for_all=physically_positive and line["separates"]
            and all(value["separates"] for value in loo.values()),
        )
    return dict(locked_predictions_sha256=pin, sites=rows,
                qualified=all(row["separates_for_all"] for row in rows.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest="stage", required=True)
    lock = stages.add_parser("predict")
    for key in (*SITES, "archive", "config", "output"):
        lock.add_argument(key, type=Path)
    score = stages.add_parser("score")
    score.add_argument("prediction", type=Path)
    score.add_argument("sha256")
    args = parser.parse_args()
    if args.stage == "predict":
        native = {site: getattr(args, site) for site in SITES}
        result = predict(native, TleArchiveReader(args.archive), args.config)
        raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(sha256(raw).hexdigest())
    else:
        print(json.dumps(reveal(args.prediction, args.sha256), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
