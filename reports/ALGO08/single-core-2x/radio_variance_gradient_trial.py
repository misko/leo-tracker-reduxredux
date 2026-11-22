"""Check analytic variance refinement on the released matched receiver evidence."""

import argparse
import json
import os
import runpy
import subprocess
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch

from . import solver_deployed_margin_trial as margins
from .residual_attribution_trial import read, write

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2]
RELEASE = margins.RELEASE
VARIANT = SOURCE / "tools/pipeline_eval/variants/experimental/analytic_radio_variance.py"
CONTROL = HERE / "measurements/solver-deployed-margin-recovery.json"
NOISE_SHA256 = "9e5256d3814031936561b233e2913713c447b18be73d6ab4939813cb34e88d1b"
PHYSICAL_REFERENCE_SHA256 = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
CASES = ("DS30-0374", "DS30-0008", "south")
SOLVES = ("DS30-0374", "south")
ARMS = ("c0", "fitted_c")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def pair_paths(bench):
    physical = bench.parent / "ds30-v2-stage-terminal-977e7d"
    return {case: physical / case / "pair.json" for case in CASES[:2]} | {
        "south": bench / "spectral-terminal-south-inside/pair.json",
    }


def bound_inputs(path, control):
    from leo.contracts.digests import canonical_digest

    if digest(path) != control["pair_sha256"]:
        raise ValueError("Expected the matched margin-recovery pair")
    pair, archive, offer, native = margins.read_inputs(path)
    expected = control["prepared_input_differential"]
    identities = {key: canonical_digest(value) for key, value in native.items()}
    if (identities != expected["native"] or pair["archive"] != expected["archive"]
            or offer != expected["offer"]):
        raise ValueError("Saved orbit, offer or native detections changed")
    return pair, archive, offer, native


def verify_noise(module):
    if digest(Path(module.__file__)) != NOISE_SHA256:
        raise ValueError("Unexpected deployed radio fit or BIC source")


def get_profile(noise, tracks, observations, fit):
    captured = []

    def measure(m, y):
        fitted = fit(m, y)
        captured.append((m, y, fitted))
        return fitted

    with patch.object(noise, "fit_variance", measure):
        result = noise.estimate_noise(tracks, observations)
    if len(captured) != 1:
        raise ValueError("Expected one fitted radio profile on the matched observations")
    return result, captured[0]


def run_fit(noise, tracks, observations, stock, analytic):
    import numpy as np

    model, inputs = {}, None
    for name, method in (("stock", stock), ("analytic", analytic["fit_variance"])):
        result, (m, y, fitted) = get_profile(noise, tracks, observations, method)
        if inputs is not None and not all(
            np.array_equal(a, b) for a, b in zip(inputs, (m, y), strict=True)
        ):
            raise ValueError("Noise fit inputs changed across solvers")
        inputs = m, y
        floor, strength = fitted
        shape = analytic["RadioProfile"](m, y)
        ratio = strength / floor
        objective, _ = shape.profile(ratio, dtype=np.longdouble)
        derivative = shape.gradient(ratio, moving_cap=ratio > 1.)
        model[name] = dict(parameters=fitted.tolist(), ratio=float(ratio),
                           profile_loss=float(objective), profile_gradient=derivative,
                           noise=margins.readout(result), sample_count=len(m))

    times = {"stock": [], "analytic": []}
    functions = {"stock": stock, "analytic": analytic["fit_variance"]}
    for repeat in range(7):
        order = tuple(functions) if repeat % 2 == 0 else tuple(reversed(functions))
        for name in order:
            start = process_time_ns()
            fitted = functions[name](*inputs)
            times[name].append(process_time_ns() - start)
            if fitted.tolist() != model[name]["parameters"]:
                raise ValueError("Repeated profile fit is not deterministic")
    for name, row in model.items():
        row.update(fit_cpu_ns=times[name], median_fit_cpu_ns=median(times[name]))
    return model


def metric_comparison(measured, observations):
    import numpy as np

    sigmas = {}
    for name in ("stock", "analytic"):
        rows = []
        for arm in ("baseline", "candidate"):
            floor, strength = measured[arm][name]["parameters"]
            by_margin = np.asarray([r["fractional_margin"] for r in observations[arm]])
            rows.append(np.sqrt(np.clip(floor + strength / by_margin, 40**2, 600**2)))
        sigmas[name] = float(np.max(abs(rows[0] - rows[1])))
    loss = {arm: value["analytic"]["profile_loss"] - value["stock"]["profile_loss"]
            for arm, value in measured.items()}
    gates = {
        "profile_likelihood": all(loss[arm] <= (
            16 * np.finfo(float).eps * abs(measured[arm]["stock"]["profile_loss"])
        ) for arm in measured),
        "bic_choice": all(row["stock"]["noise"]["heteroscedastic_selected"]
                          == row["analytic"]["noise"]["heteroscedastic_selected"]
                          for row in measured.values()),
    }
    return dict(maximum_sigma_delta_hz=sigmas, objective_delta=loss, gates=gates)


def prepare(bench, output):
    import numpy as np

    from leo.analysis.localization_v3 import noise
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest

    verify_noise(noise)
    stock = noise.fit_variance
    analytic = runpy.run_path(str(VARIANT))
    config = TrackConfig(**read(RELEASE / "assets/tracks.json")["config"])
    controls = read(CONTROL)["cases"]
    results = {}
    for case, path in pair_paths(bench).items():
        _, _, _, native = bound_inputs(path, controls[case])
        prepared = {arm: prepare_tracks(doc, config) for arm, doc in native.items()}
        graph = {arm: canonical_digest(json.loads(json.dumps(row["tracks"], default=_json_value)))
                 for arm, row in prepared.items()}
        expected = controls[case]["prepared_input_differential"]
        if graph != expected["graph"] or graph["baseline"] != graph["candidate"]:
            raise ValueError("The released matched Graph support changed")
        tracks = prepared["candidate"]["tracks"]
        candidate = prepared["candidate"]["observations"]
        baseline = margins.matched_margins(prepared["baseline"]["observations"], candidate)
        observations = {"baseline": baseline, "candidate": candidate}
        measured = {arm: run_fit(noise, tracks, rows, stock, analytic)
                    for arm, rows in observations.items()}
        if any(row["stock"]["noise"] != expected["noise"][arm] for arm, row in measured.items()):
            raise ValueError("Stock radio fit differs from the archived matched control")
        metrics = metric_comparison(measured, observations)
        gates = metrics["gates"]
        sigma = metrics["maximum_sigma_delta_hz"]
        if case == "south":
            gates["constant_noise"] = all(
                row["analytic"]["parameters"][1] == 0
                and row["stock"]["noise"] == row["analytic"]["noise"] for row in measured.values()
            )
        else:
            gates["sigma_sensitivity"] = (
                sigma["stock"] > 0 and sigma["analytic"] <= sigma["stock"] / 100
            )
        margin_delta = [a["fractional_margin"] - b["fractional_margin"]
                        for a, b in zip(baseline, candidate, strict=True)]
        results[case] = metrics | dict(
            observations=len(candidate), graph=graph, native=expected["native"],
            pair_sha256=controls[case]["pair_sha256"], fits=measured,
            max_margin_delta=float(np.max(np.abs(margin_delta))),
        )
    advanced = all(all(row["gates"].values()) for row in results.values())
    write(output, dict(variant_sha256=digest(VARIANT), stock_sha256=NOISE_SHA256,
                       control_sha256=digest(CONTROL), proceeded=advanced, cases=results))


def worker(native, spec, archive, offer, output, variant_sha256):
    from tools.pipeline_eval.variants.experimental import lean_startup

    if digest(VARIANT) != variant_sha256:
        raise ValueError("Analytic variance implementation differs from its preparation lock")
    original_install = lean_startup.install
    fits = []
    with ExitStack() as stack:
        def install_then_bind():
            original_install()
            from leo.analysis.localization_v3 import noise

            verify_noise(noise)
            analytic = runpy.run_path(str(VARIANT))["fit_variance"]

            def fit(m, y):
                before = process_time_ns()
                result = analytic(m, y)
                fits.append(dict(fit_cpu_ns=process_time_ns() - before,
                                 noise_samples=len(m), parameters=result.tolist()))
                return result

            stack.enter_context(patch.object(noise, "fit_variance", fit))

        stack.enter_context(patch.object(lean_startup, "install", install_then_bind))
        replay = runpy.run_path(str(HERE / "residual_attribution_trial.py"))["worker"]
        replay(native, spec, archive, offer, output, include_evidence=True)
    result = read(output)
    if not fits:
        raise ValueError("Complete solver did not call the analytic radio profile")
    output.unlink()
    write(output, result | {"radio_fits": fits})


def run_saved(frozen, native, offer, archive, variant_sha256):
    env = dict(os.environ, PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}:{SOURCE}",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        detections, region, output = (scratch / name for name in ("native", "offer", "solved"))
        write(detections, native)
        write(region, offer)
        command = [str(RELEASE / "venv/bin/python"), "-BPs", "-m",
                   "reports.ALGO08.single-core-2x.radio_variance_gradient_trial",
                   "worker", *map(str, (detections, frozen / "spec.json", archive, region, output)),
                   variant_sha256]
        subprocess.run(command, env=env, timeout=120, check=True)
        return read(output)


def published_references(pairs):
    physical = SOURCE / "reports/2026_11_21_ds30_full/reference-audit.json"
    if digest(physical) != PHYSICAL_REFERENCE_SHA256:
        raise ValueError("The released physical reference authority changed")
    reference, = (row["reference"] for row in read(physical)["cases"]
                  if row["dataset_label"] == "DS30-0374" and row["authority_eligible"])
    south_path = HERE / "measurements/spectral-terminal-south-audit.json"
    south = read(south_path)
    if (south["raw_authority"] != pairs["south"]["runs"]["candidate"]["raw_authority"]
            or south["region"] != pairs["south"]["runs"]["candidate"]["receipt"]["region"]):
        raise ValueError("The southern published reference is bound to a different input")
    return {
        "DS30-0374": ([reference["latitude_deg"], reference["longitude_deg"]], digest(physical)),
        "south": (south["reference_latlon"], digest(south_path)),
    }


def solve(bench, prepared, output):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity
    from tools.pipeline_eval.scoring import distance_km

    from .screened_stock_salvage_trial import require_spec
    from .screened_tiled_graph_trial import KEYS, evidence_digests

    prep = read(prepared)
    if (not prep["proceeded"] or prep["variant_sha256"] != digest(VARIANT)
            or prep["control_sha256"] != digest(CONTROL)
            or not all(all(prep["cases"][case]["gates"].values()) for case in CASES)):
        raise ValueError("The prespecified preparation checks did not pass")
    controls = read(CONTROL)["cases"]
    physical = bench / "integration-frame-plane-terminal-veto"
    southern = bench / "integration-spectral-vectors-wrapped-longitude"
    pairs, trials = {}, {}
    for case, frozen in zip(SOLVES, (physical, southern), strict=True):
        control = controls[case]
        spec = control["restored_native_specification"]
        require_spec(frozen, spec)
        path = pair_paths(bench)[case]
        pairs[case], archive, offer, native = bound_inputs(path, control)
        result = run_saved(frozen, native["candidate"], offer, archive, prep["variant_sha256"])
        if archive_identity(archive) != pairs[case]["archive"]:
            raise ValueError("The saved-solve archive changed")
        if (not result["radio_fits"] or any(
            fit["parameters"] != prep["cases"][case]["fits"]["candidate"]["analytic"]["parameters"]
            for fit in result["radio_fits"]
        )):
            raise ValueError("The solver used a different analytic variance fit")
        trial = {k: result.get(k) for k in (
            *KEYS, "solver_cpu_s", "solver_wall_s", "radio_fits",
        )}
        trial["science"] = evidence_digests(result)
        trials[case] = dict(result=trial, specification=spec, offer=offer,
                            pair_sha256=control["pair_sha256"], archive=pairs[case]["archive"])
    references = published_references(pairs)
    for case, record in trials.items():
        reference, reference_pin = references[case]
        control = controls[case]
        result = record["result"]
        deploy, prior = (pairs[case]["runs"][name] for name in ("baseline", "candidate"))
        fixed = dict(arms=control["restored_arms"], owners=control["owners"],
                     scientific_digests=control["restored_science"])
        record["reference_sha256"] = reference_pin
        record["comparisons"] = {}
        comparisons = {"deployed": deploy, "published_candidate": prior, "exact_margin": fixed}
        for name, old in comparisons.items():
            difference = {a: distance_km(old["arms"][a]["latlon"], result["arms"][a]["latlon"])
                          for a in ARMS}
            scores = {
                arm: {label: distance_km(row["arms"][arm]["latlon"], reference)
                      for label, row in (("before", old), ("analytic", result))}
                for arm in ARMS
            }
            science = old["scientific_digests"]
            record["comparisons"][name] = dict(
                arms=old["arms"], displacement_km=difference, horizontal_error_km=scores,
                exact_arms=result["arms"] == old["arms"],
                exact_owners=result["owners"] == old["owners"],
                exact_path=result["science"].get("position_path") == science["path"],
                exact_grid=result["science"].get("position_grid") == science["grid"],
            )
    write(output, dict(preparation_sha256=digest(prepared), variant_sha256=prep["variant_sha256"],
                       cases=trials))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest="stage", required=True)
    for name, args in {
        "prepare": ("bench", "output"),
        "solve": ("bench", "prepared", "output"),
        "worker": ("native", "spec", "archive", "offer", "output"),
    }.items():
        stage = stages.add_parser(name)
        for arg in args:
            stage.add_argument(arg, type=Path)
        if name == "worker":
            stage.add_argument("variant_sha256")
    args = parser.parse_args()
    options = vars(args)
    {"prepare": prepare, "solve": solve, "worker": worker}[options.pop("stage")](**options)


if __name__ == "__main__":
    main()
