"""Run the public, research-only generator orbit counterfactual on saved detections."""

import argparse
import json
import os
import runpy
import subprocess
from contextlib import ExitStack, contextmanager
from copy import copy
from datetime import datetime
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
ARMS = ("c0", "fitted_c")
PROTOCOL = "d91acd850cce712cad70b4db9ffa62f15d95d5569c490b23275ece466604df64"
TRUTH = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
GENERATOR = {
    "collection_utc_ns": 1794649020001090000,
    "metadata_sha256": "d802787439bb7d3db58445cd836e307c0a34d53f3765d540a26d95ddfaf70f7b",
    "raw_sha256": "adc4d9c1c52af94704d8eb584f831f313cd3b11a0a5630842ca9afa530fc7339",
}
BUNDLES = dict(
    original=(
        "exact-curved-lookahead",
        "48fed3c62639ef81fb99e4b76921bcacd999e769a78ebb607b2b886b6f0951f0",
        "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    ),
    rotated=(
        "spectral-terminal",
        "321f55cfe47a98f31d250dacf53efed30307545298d7ec64b1a3ea88300cc010",
        "sha256:23fadeb79c76c343760dc3fb107f7dfb170b0ba4eec22a4dc3df244c2187cf24",
    ),
)
CONTROL = {
    "original": (
        "exact-curved-lookahead-south-offers.json",
        "5181abf1c8a36d45dfe140e8851f0a423b69ec69b8ca231a3f87bcc9fdcecca9",
    ),
    "rotated": (
        "north-south-faces.json",
        "a2923036a2f9df121912f519c63bd8b4cb6a7c49a20b65989086c2e34c544f63",
    ),
}


def read(path, pin=None):
    raw = path.read_bytes()
    if pin is not None and sha256(raw).hexdigest() != pin:
        raise ValueError(f"Pinned public input changed: {path.name}")
    return json.loads(raw)


def write(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, sort_keys=True, indent=2, allow_nan=False), file=stream)


def later_elements(cutoff):
    from tools.pipeline_eval.qualification import cold_scenes
    from tools.pipeline_eval.qualification.waveform_site_trial import revised

    baseline = read(cold_scenes.SNAPSHOT)
    received = cold_scenes._stamp(datetime.fromisoformat(baseline["retrieved_at"]))
    blob, collected, authority = revised(received, cold_scenes.CATALOG_SHA256)
    if collected <= cutoff or any(authority[k] != v for k, v in GENERATOR.items()):
        raise ValueError("Expected the known, later public waveform generator TLE")
    satellites = cold_scenes._constellation(blob, collected)
    numbers = {sat.satnum: sat for sat in satellites}
    if len(numbers) != len(satellites):
        raise ValueError("Expected unique IDs in the generator catalogue")
    return numbers, authority


def select_catalogue(catalogue, mask):
    from leo.sky.propagation import ElementSetCatalogue

    indices = np.flatnonzero(mask)
    return ElementSetCatalogue(
        *(
            tuple(values[i] for i in indices)
            for values in (
                catalogue.names,
                catalogue.satellite_numbers,
                catalogue.satellites,
            )
        ),
    )


def oracle_states(numbers, position, velocity, good, origin, times, generator):
    """Replace every matched, previously usable state row with generator geometry."""
    from leo.analysis.localization_v3.orbits import ecef_states
    from leo.sky.propagation import ElementSetCatalogue

    indices = [i for i, n in enumerate(numbers) if good[i] and n in generator]
    if not indices:
        return position, velocity
    matched = tuple(int(numbers[i]) for i in indices)
    oracle = ElementSetCatalogue(
        tuple(map(str, matched)), matched, tuple(generator[n] for n in matched)
    )
    p, v, usable = ecef_states(oracle, origin, times)
    if not usable.all() or not np.isfinite(p).all() or not np.isfinite(v).all():
        raise RuntimeError("A matched causal candidate has unusable ORACLE states")
    result_p, result_v = position.copy(), velocity.copy()
    result_p[indices], result_v[indices] = p, v
    return result_p, result_v


def sky_pair(bank, origin, generator, *, use_oracle, intersection):
    numbers = bank["norad"]
    mask = np.isin(numbers, list(generator))
    if intersection:
        if not mask.any():
            raise ValueError("No common candidates in regional causal and ORACLE catalogues")
        bank = {key: values if key == "time_s" else values[mask] for key, values in bank.items()}
    if not use_oracle:
        return bank, bank
    p, v = oracle_states(
        bank["norad"],
        bank["position_km"],
        bank["velocity_km_s"],
        np.ones(len(bank["norad"]), bool),
        origin,
        bank["time_s"],
        generator,
    )
    return bank, dict(bank, position_km=p, velocity_km_s=v)


def causal_prior(operation):
    def evaluate(scan, *args, **kwargs):
        return operation(getattr(scan, "_oracle_causal_priors", scan), *args, **kwargs)

    return evaluate


@contextmanager
def trial_geometry(generator, use_oracle, intersection, trace):
    from leo.analysis.localization_v3 import (
        family_cavity,
        history_position,
        marginal,
        new_family,
        orbit_modes,
        prediction,
        retained_position,
    )
    from leo.operations import localization_v3_inputs
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_reassignment as guard

    build = localization_v3_inputs.regional_bank
    make_scan = v5_core.scan_context
    rank = v5_core.ranked_initial_nodes
    infer = v5_core.infer
    guard_score = guard.evaluate_veto
    guard_geometry = guard.orbit_geometry
    guard_states = guard.ecef_states
    cached = None

    def inventory(catalogue, *args, **kwargs):
        numbers = catalogue.satellite_numbers
        trace["catalogue"] = dict(
            count=len(numbers),
            missing=[n for n in numbers if n not in generator],
            generator_only=sorted(set(generator) - set(numbers)),
        )
        return build(catalogue, *args, **kwargs)

    def scan_context(prepared, region, noise, bound, previous):
        nonlocal cached
        sky = prepared["sky"]
        raw = sky["bank"]
        cutoff = sky["metadata"]["cutoff_utc_ns"]
        if cutoff >= GENERATOR["collection_utc_ns"]:
            raise ValueError("The ORACLE catalogue must postdate the original cutoff")
        if cached is None or cached[0] is not raw:
            causal, alternate = sky_pair(
                raw,
                sky["metadata"]["origin_utc_ns"],
                generator,
                use_oracle=use_oracle,
                intersection=intersection,
            )
            cached = raw, causal, alternate
        _, causal, alternate = cached
        trace["regional_bank"] = dict(
            cutoff_utc_ns=cutoff,
            original_count=len(raw["norad"]),
            count=len(causal["norad"]),
            numbers=causal["norad"].tolist(),
            missing=[int(n) for n in raw["norad"] if n not in generator],
        )
        context = make_scan(
            dict(prepared, sky=dict(sky, bank=alternate)), region, noise, bound, previous
        )
        if use_oracle:
            prior_view = copy(context)
            prior_view.sky = causal
            context._oracle_causal_priors = prior_view
        return context

    def ranked(scan):
        result = rank(scan)
        trace["ranked_norads"] = [
            sorted({r["candidate_norad"] for r in node["seed"]["rows"]}) for node in result
        ]
        return result

    def record_inference(*args, selected_evidence=None, **kwargs):
        def record(ready, signed, fit):
            arms = signed["arms"] if fit is None else fit["policy_arms"]
            keys = (
                "endpoint_latlon",
                "endpoint_east_north_km",
                "RMS_hz",
                "active_points",
                "negative_twice_elbo",
            )
            trace["pre_terminal_arms"] = {a: {key: arms[a].get(key) for key in keys} for a in ARMS}
            if selected_evidence is not None:
                selected_evidence(ready, signed, fit)

        return infer(*args, selected_evidence=record, **kwargs)

    def score(catalogue_tracks, catalogue, region):
        if intersection:
            catalogue = select_catalogue(
                catalogue, [n in generator for n in catalogue.satellite_numbers]
            )
        trace["guard_input_count"] = len(catalogue.satellite_numbers)
        return guard_score(catalogue_tracks, catalogue, region)

    def geometry(*args, **kwargs):
        calls = []

        def propagate(catalogue, origin, times):
            p, v, good = guard_states(catalogue, origin, times)
            calls.append(len(catalogue.satellite_numbers))
            if len(calls) == 2:
                trace["guard_fine_missing"] = [
                    n for n in catalogue.satellite_numbers if n not in generator
                ]
                if use_oracle:
                    p, v = oracle_states(
                        catalogue.satellite_numbers, p, v, good, origin, times, generator
                    )
            return p, v, good

        with patch.object(guard, "ecef_states", propagate):
            result = guard_geometry(*args, **kwargs)
        if len(calls) not in (1, 2):
            raise RuntimeError(
                "The released guard no longer separates causal screen and fine projection"
            )
        trace["guard_state_rosters"] = calls
        return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(localization_v3_inputs, "regional_bank", inventory))
        stack.enter_context(patch.object(v5_core, "scan_context", scan_context))
        stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", ranked))
        stack.enter_context(patch.object(v5_core, "infer", record_inference))
        stack.enter_context(patch.object(guard, "evaluate_veto", score))
        stack.enter_context(patch.object(guard, "orbit_geometry", geometry))
        for module in (orbit_modes, retained_position):
            stack.enter_context(
                patch.object(module, "previous_bank", causal_prior(module.previous_bank))
            )
        for module in (
            orbit_modes,
            family_cavity,
            history_position,
            marginal,
            new_family,
            prediction,
        ):
            stack.enter_context(
                patch.object(module, "build_modes", causal_prior(module.build_modes))
            )
        yield


def worker(native, spec, archive, offer, output, mode, cutoff):
    from tools.pipeline_eval.qualification import experimental_publication

    saved = runpy.run_path(str(HERE / "residual_attribution_trial.py"))
    publish = experimental_publication.run
    authority, trace = {}, {}

    def experiment(*args, **kwargs):
        generator, source = later_elements(cutoff)
        authority.update(source)
        with trial_geometry(generator, mode != "causal-intersection", mode != "oracle-full", trace):
            return publish(*args, **kwargs)

    result = output.with_suffix(".solver.json")
    with patch.object(experimental_publication, "run", experiment):
        saved["worker"](
            native, spec, archive, offer, result, include_evidence=True, guard_evidence=True
        )
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest

    data = read(result)
    result.unlink()
    evidence = data.pop("evidence", {})
    data["science_digests"] = {
        key: canonical_digest(
            {k: v for k, v in value.items() if k not in ("binding", "elapsed_seconds")}
        )
        for key, value in evidence.items()
    }
    if trace["regional_bank"]["cutoff_utc_ns"] != cutoff or not trace.get("ranked_norads"):
        raise ValueError("Expected a complete, cutoff-matched discovery and decision trace")
    result = dict(mode=mode, ORACLE=authority, trace=trace, solver=data)
    write(output, json.loads(json.dumps(result, default=_json_value, allow_nan=False)))


def inputs(bench, orientation):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    saved = import_module("reports.ALGO08.single-core-2x.residual_attribution_trial")
    check = import_module("reports.ALGO08.single-core-2x.screened_stock_salvage_trial")
    family, pair_pin, spec = BUNDLES[orientation]
    pair_path = bench / f"{family}-south-inside/pair.json"
    bundle = bench / (
        "integration-exact-curved-lookahead"
        if orientation == "original"
        else "integration-spectral-vectors-terminal-veto"
    )
    pair = read(pair_path, pair_pin)
    check.require_spec(bundle, spec)
    if pair["candidate_specification_digest"] != spec:
        raise ValueError("Archived causal pair used a different solver")
    archive = Path(pair["archive"]["root"])
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Public causal archive changed after recording")
    candidate = pair["runs"]["candidate"]
    native = saved.saved_native(pair_path, "candidate", candidate)
    key, pin = CONTROL[orientation]
    controls = read(MEASUREMENTS / key, pin)
    if controls["specification"] != spec:
        raise ValueError("Archived saved solves used a different solver")
    if orientation == "original":
        if (
            controls["pair_sha256"] != pair_pin
            or controls["native_sha256"] != canonical_digest(native)
            or controls["archive"] != pair["archive"]
        ):
            raise ValueError("Near-outside control does not bind the paired native and archive")
        outside = controls["results"]["south-mirror-outside"]
        receipt = candidate["receipt"]
        detail = FastStandardAnalysisStore(pair_path.parent / "candidate").detail(receipt["run_id"])
        inside = dict(
            offer=receipt["region"],
            status="ok" if receipt["decision"] == "complete" else "withheld",
            arms=candidate["arms"],
            owners=candidate["owners"],
            reason=candidate["reason"],
            associated={a: detail["arms"][a]["associated_points"] for a in ARMS},
        )
    else:
        rotated = controls["sites"]["south-candidate"]
        if (
            rotated["pair_sha256"] != pair_pin
            or rotated["native_sha256"] != canonical_digest(native)
            or rotated["archive"] != pair["archive"]
        ):
            raise ValueError("Rotated controls do not bind the paired native and archive")
        inside, outside = (
            dict(row, offer=row["region"])
            for row in [rotated["offers"][name] for name in ("inside", "outside")]
        )
    return pair, bundle, native, dict(inside=inside, outside=outside)


def run(bench, out, orientation, scope):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    protocol = HERE / "oracle-orbit-solve-protocol.md"
    if sha256(protocol.read_bytes()).hexdigest() != PROTOCOL:
        raise ValueError("The preregistered oracle protocol changed")
    pair, bundle, native, controls = inputs(bench, orientation)
    spec = pair["candidate_specification_digest"]
    archive = pair["archive"]
    cutoff = native["clock_anchor"]["before"]["realtime_ns"]
    modes = ("oracle-full",) if scope == "full" else ("causal-intersection", "oracle-intersection")
    offers = {name: row["offer"] for name, row in controls.items()}
    out.mkdir(exist_ok=False)
    plan = dict(
        orientation=orientation,
        scope=scope,
        specification=spec,
        offers=offers,
        modes=modes,
        protocol_sha256=PROTOCOL,
        generator=GENERATOR,
        archive=archive,
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        native_sha256=canonical_digest(native),
        cutoff_utc_ns=cutoff,
        recording_name=Path(pair["recording"]).name,
        pair_sha256=BUNDLES[orientation][1],
        prior_control_sha256=CONTROL[orientation][1],
    )
    write(out / "plan.json", plan)
    write(out / "native.json", native)
    env = dict(
        os.environ,
        PYTHONPATH=f"{bundle}:{RELEASE / 'src'}:{RELEASE}",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
    )
    for key in (
        "ALGO08_EVALUATION_LATITUDE",
        "ALGO08_EVALUATION_LONGITUDE",
        "ALGO08_REGION_FILE",
        "ALGO08_EXPERIMENT_CONFIG",
    ):
        env.pop(key, None)
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    for name, offer in offers.items():
        roi = out / f"{name}.offer.json"
        write(roi, offer)
        for mode in modes:
            args = (
                out / "native.json",
                bundle / "spec.json",
                archive["root"],
                roi,
                out / f"{name}.{mode}.json",
                mode,
                cutoff,
            )
            subprocess.run(command + list(map(str, args)), env=env, check=True, timeout=75)
    if archive_identity(Path(archive["root"])) != archive:
        raise ValueError("Public causal archive changed during the research solve")
    for name in offers:
        if scope == "intersection":
            a, b = (read(out / f"{name}.{mode}.json")["trace"]["regional_bank"] for mode in modes)
            if a != b or not a["missing"] or set(a["numbers"]) & set(a["missing"]):
                raise ValueError("The causal and oracle intersection bank identities differ")


def score(bench, out, output):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    plan = read(out / "plan.json")
    _, _, _, controls = inputs(bench, plan["orientation"])
    if (
        plan["protocol_sha256"] != PROTOCOL
        or plan["generator"] != GENERATOR
        or {name: r["offer"] for name, r in controls.items()} != plan["offers"]
    ):
        raise ValueError("The study plan or offers do not match frozen public inputs")
    results = {
        name: {mode: read(out / f"{name}.{mode}.json") for mode in plan["modes"]}
        for name in controls
    }
    truth_path = HERE.parent / "regional-release/scoring-key.json"
    answers = read(truth_path, TRUTH)["answers"]
    (truth,) = {
        tuple(r["truth"]) for r in answers.values() if r["recording"] == plan["recording_name"]
    }

    def location(value, offer):
        latlon = value.get("latlon")
        if latlon is None:
            return dict(value, error_km=None, clearance_km=None)
        return dict(
            value,
            error_km=distance_km(latlon, truth),
            clearance_km=face_clearance_km(offer, latlon),
        )

    for name, modes in results.items():
        control = controls[name]
        offer = control["offer"]
        clearance = face_clearance_km(offer, truth)
        if not np.isclose(clearance, 0.1 if name == "inside" else -0.1, atol=1e-9, rtol=0):
            raise ValueError("Published truth does not match the archived near-face designation")
        modes["archived-causal"] = {"solver": control}
        for row in modes.values():
            solver = row["solver"]
            row["truth_clearance_km"] = clearance
            row["false_fix"] = solver["status"] == "ok" and name == "outside"
            row["valid_fix"] = solver["status"] == "ok" and name == "inside"
            row["position"] = {a: location(solver["arms"][a], offer) for a in ARMS}
            terminal = row.get("trace", {}).get("pre_terminal_arms", {})
            row["pre_terminal_position"] = {
                a: location(dict(arm, latlon=arm["endpoint_latlon"]), offer)
                for a, arm in terminal.items()
            }
    write(output, dict(plan=plan, truth_latlon=list(truth), offers=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    replay = commands.add_parser("run")
    for key in ("bench", "out"):
        replay.add_argument(key, type=lambda v: Path(v).resolve())
    replay.add_argument("orientation", choices=BUNDLES)
    replay.add_argument("scope", choices=("full", "intersection"))
    scoring = commands.add_parser("score")
    for key in ("bench", "out", "output"):
        scoring.add_argument(key, type=Path)
    child = commands.add_parser("worker")
    for key in ("native", "spec", "archive", "offer", "output"):
        child.add_argument(key, type=Path)
    child.add_argument(
        "mode", choices=("oracle-full", "oracle-intersection", "causal-intersection")
    )
    child.add_argument("cutoff", type=int)
    args = vars(parser.parse_args())
    action = args.pop("action")
    {"run": run, "score": score, "worker": worker}[action](**args)


if __name__ == "__main__":
    main()
