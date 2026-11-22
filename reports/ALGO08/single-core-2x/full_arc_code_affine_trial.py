"""Separate per-emitter delay trend from full-arc geometric curvature."""

import argparse
import gzip
import json
from functools import partial
from hashlib import sha256
from pathlib import Path

import numpy as np

from leo.operations.tle_archive import TleArchiveReader

from . import full_arc_code_trial as trial

COMMON_CLOCK_PIN = "945ead8ab2521a8e0b8fa62d0c83b0930fc0c39e4ce5bbec696795c297666102"
FACES = ("u0.0", "u1.0")


def fit(arcs, model, rate, *, observed=None):
    error, rates = trial.code.frame_residual(
        arcs, model, rate, per_arc=True, observed=observed,
    )
    return trial.held(arcs, error) | {"slopes_samples_per_s": rates}


def remove_orbit(results, omitted):
    # Rate and intercept fits are independent by arc in this variant. Removing
    # an orbit leaves exactly the original fits on all other training rows.
    output = {}
    for name, result in results.items():
        retained = [v for orbit, v in result["orbit_mse"].items() if orbit != omitted]
        output[name] = {"held_rms_samples": float(np.sqrt(np.mean(retained)))}
    return output


def infer(site, spec, pairs, document, configuration, archive, *, baseline):
    arcs, rate, owners, snapshots, positions, delays = trial.geometry(
        spec, pairs, document, configuration, archive,
    )
    support = trial.arc_summary(arcs)
    prior = baseline["sites"][site]
    if (prior["positions"] != positions or prior["arcs"] != support
            or prior["native_sha256"] != spec["native_sha256"]
            or prior["causal_snapshots"] != snapshots):
        raise ValueError("Affine model must use the exact sealed common-clock support")
    results = {name: fit(arcs, model, rate) for name, model in delays.items()}
    loo = {orbit: trial.outcome(remove_orbit(results, orbit)) for orbit in owners}
    carrier = [trial.accumulated_carrier(arc, rate) for arc in arcs]
    diagnostics = {
        "code_against_carrier": {
            str(sign): fit(arcs, [sign * values for values in carrier], rate)
            for sign in (1., -1.)
        },
        "carrier_against_geometry": {
            name: fit(arcs, delays[name], rate, observed=carrier) for name in FACES
        },
        "curvature_separation": {
            source: fit(arcs, delays[target], rate, observed=delays[source])
            for source, target in (FACES, FACES[::-1])
        },
    }
    steps = np.asarray([rate * trial.code.FOLD_HZ / arc.rf_hz for arc in arcs])
    slope = np.asarray(diagnostics["code_against_carrier"]["1.0"]["slopes_samples_per_s"])
    alias = np.rint(slope / steps)
    diagnostic_alias = dict(aliases=alias.astype(int).tolist(),
                            remainder_samples_per_s=(slope - alias * steps).tolist())
    difference = {
        name: (np.asarray(results[name]["slopes_samples_per_s"])
               - prior["results"][name]["drift_samples_per_s"]).tolist()
        for name in FACES
    }
    return dict(site=site, arcs=support, positions=positions, results=results,
                causal_snapshots=snapshots, native_sha256=spec["native_sha256"],
                outcome=trial.outcome(results), leave_one_satellite_out=loo,
                diagnostic_alias=diagnostic_alias, slopes_minus_common_rate=difference,
                **diagnostics)


def predict(north, south, archive, config, output):
    base = trial.study.inputs.MEASUREMENTS / "full-arc-code-prediction.json.gz"
    locked = gzip.decompress(base.read_bytes())
    if sha256(locked).hexdigest() != COMMON_CLOCK_PIN:
        raise ValueError("The common-clock experiment differs from its sealed prediction")
    model = partial(infer, baseline=json.loads(locked))
    results = trial.predict(dict(north=north, south=south), TleArchiveReader(archive),
                            config, model=model)
    result = dict(results, common_clock_prediction_sha256=COMMON_CLOCK_PIN)
    raw = json.dumps(result, sort_keys=True, allow_nan=False).encode()
    with output.open("xb") as stream:
        stream.write(raw)
    print(sha256(raw).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    fit = sub.add_parser("predict")
    for name in ("north", "south", "archive", "config", "output"):
        fit.add_argument(name, type=Path)
    score = sub.add_parser("score")
    score.add_argument("prediction", type=Path)
    score.add_argument("sha256")
    args = parser.parse_args()
    if args.stage == "predict":
        options = vars(args)
        del options["stage"]
        predict(**options)
    else:
        print(json.dumps(trial.reveal(args.prediction, args.sha256), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
