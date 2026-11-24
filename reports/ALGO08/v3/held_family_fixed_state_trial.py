"""Compare one actual held-family substage from an intact selected state."""

import argparse
from collections import Counter
from contextlib import ExitStack, nullcontext
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
ORDERS = (False, True, True, False)


def prepare_context(prepared, region, bound, archived):
    import numpy as np
    from blind_joint_finish import digest
    from grid_fixed_context_trial import selected
    from leo.analysis.localization_v3.discovery import zero_state
    from leo.analysis.localization_v3.history_position import forecast_phase_mean
    from leo.analysis.localization_v3.retained_position import phase_widths
    from leo.analysis.localization_v3.signed_phase import adjust_means
    from tools.pipeline_eval.variants import v5_core

    selected_fit = archived["lean_final_fit"]
    model, arms = selected_fit["model"], selected_fit["arms"]
    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "genuine_previous")
    measured = archived["lean_attempts"][0]
    order = measured["support"]["predictive_labels"]
    selection = measured["signed"]["selection"]
    if not selection["qualified"] or measured["signed"]["status"] != "accepted":
        raise ValueError("The signed genuine witness was not accepted")
    states = {}
    for arm, witness in arms.items():
        p, verify = selected(scan, witness, arm, order, model, None)
        verify()
        x = np.asarray(witness["fit"]["position"])
        calculation = p.calculate(x)
        if (scan.fixed_window_noise_sha256 != witness["original_noise"]
                or scan.previous_tle_sha256 != witness["original_previous_tle"]
                or scan.origin_utc_ns != witness["timing_origin_ns"]
                or calculation["negative_twice_elbo"] != witness["fit"]["objective"]):
            raise ValueError(f"Selected archived likelihood could not be reconstructed: {arm}")
        states[arm] = p, x
    p, x = states["c0"]
    families = arms["c0"]["families"]
    powers = np.asarray([arms["c0"]["curves"][row["component"]].get("power", 1.) for row in p.rows])
    means = np.asarray([families[str(scan.norads[j])]["signed_prior_mean"] for j in p.labels])
    node = dict(seed=dict(rows=p.rows, state=zero_state(scan)), aliases=p.alias)
    candidates = {int(norad): j for j, norad in enumerate(scan.norads)}
    indices = {track["key"]: i for i, track in enumerate(scan.tracks)}
    entries = []
    for key, norad, alias in order:
        row = arms["c0"]["predictive"][key]
        entries.append(dict(track_index=indices[key], candidate_index=candidates[norad], component=key,
                            norad=norad, alias=alias, points=len(row["ids"]), observation_ids=row["ids"],
                            cross_receiver_curved_support=row["cross_receiver"]))
    width, receipts = phase_widths(scan, list(range(len(scan.norads))))
    all_means = adjust_means(forecast_phase_mean(receipts, model["shrinkage"]), receipts, model, selection)
    if not np.array_equal(all_means[p.labels], means):
        raise ValueError("Broader signed phase priors did not reproduce the selected values")
    return dict(case="SCAN", scan=scan, node=node, keep=p.keep, powers=powers, means=means, model=model,
                entries=entries, base=p, x=x, reference=p.reference, all_means=all_means,
                widths=width*model["multiplier"], signed=dict(policy_arms={a: row["fit"] for a, row in arms.items()}))


def fingerprint(value):
    import numpy as np

    if isinstance(value, (np.ndarray, np.generic, float)):
        a = np.asarray(value)
        return a.shape, a.dtype.str, sha256(a.tobytes()).hexdigest()
    if isinstance(value, dict):
        return [(key, fingerprint(item)) for key, item in value.items()]
    if isinstance(value, (tuple, list)):
        return [fingerprint(item) for item in value]
    return value


def compare(context):
    from leo.analysis.localization_v3 import family_cavity
    from leo.contracts.digests import canonical_digest
    from grid_fixed_context_trial import clock, elapsed
    from held_family_fixed_state import binding

    observations = []
    expected = None
    scan = context["scan"]
    caches = ("previous_shape_cache", "causal_uncertainty_modes", "diagnostic_phase_width_cache",
              "reference_motion_cache", "element_derivatives")
    initial = {name: getattr(scan, name) for name in caches if hasattr(scan, name)}
    for enabled in ORDERS:
        start = clock()
        family, prediction = Counter(), Counter()
        with ExitStack() as stack:
            for name, value in initial.items():
                stack.enter_context(patch.object(scan, name, dict(value)))
            counts = stack.enter_context(binding() if enabled else nullcontext(Counter()))
            entries = []

            def charged(operation, ledger):
                def run(*args, **kwargs):
                    before = process_time_ns()
                    response = operation(*args, **kwargs)
                    ledger.update(cpu_ns=process_time_ns()-before, calls=1)
                    if ledger is family:
                        entries.append({k: v for k, v in response.items() if k != "p"})
                    return response
                return run
            for name, ledger in (("family_data", family), ("candidate_prediction", prediction)):
                stack.enter_context(patch.object(family_cavity, name, charged(getattr(family_cavity, name), ledger)))
            nomination = family_cavity.nominate_families(context)
        total = elapsed(start)
        if nomination["status"] != "complete" or (enabled and counts["unsupported"]):
            raise ValueError(f"Original nomination failed or ignored candidate: {nomination.get('error')}")
        complete = fingerprint(nomination), fingerprint(entries)
        if expected is None:
            expected = complete
        if complete != expected:
            raise ValueError("Original held calibration, predictive candidate, or nomination bytes differ")
        observations.append(dict(mode="candidate" if enabled else "stock", inclusive=total,
                                 family=dict(family), prediction=dict(prediction), work=dict(counts)))
    rows = nomination["families"]
    return dict(observations=observations, identical=True, output_sha256=canonical_digest(expected),
                nominated_families=len(rows), hypotheses=sum(len(row["candidates"]) for row in rows),
                positive_offers=sum(row["best"] is not None and row["predictive_gain"] > 0 for row in rows),
                held_points=sum(row["held_points"] for row in rows))


def run(output):
    import empty_bootstrap as boot
    from aperture_trial import solve, write
    from exact_named_route import exact_ports, resident_path
    from grid_fixed_context_trial import WITNESS, WITNESS_PIN, clock, elapsed
    from history_risk_0169_input import bind
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    start = clock()
    _, spec, _, publication, _ = boot.load_runtime()
    from leo.contracts.digests import canonical_digest
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Use a fresh tmpfs receipt path")
    bound, req = bind()
    native = json.loads(resident_path(Path(req["native_file"])).read_bytes())
    offer = json.loads(resident_path(Path(req["offer_file"])).read_bytes())
    archived = json.loads(boot.checked(resident_path(WITNESS), WITNESS_PIN))["solves"][0]
    if canonical_digest(native) != "sha256:"+req["native_sha256"]:
        raise ValueError("The saved input does not reproduce the original detector")
    archive = resident_path(Path(bound["archive"]))
    spec["startup"] = "stock"
    ordinary = algo08_position.solve
    record = dict(case="DS30-0169", original_archive=req["local_archive"]["snapshots_sha256"],
                  witness_sha256=WITNESS_PIN, native_sha256=req["native_sha256"], offer_sha256=req["offer_sha256"],
                  admission=elapsed(start), sources={path.name: sha256(path.read_bytes()).hexdigest() for path in (
                      Path(__file__), HERE/"held_family_fixed_state.py", HERE/"held-family-fixed-state-protocol.md")})
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, verified_tle=Counter())

    def observe(document, reader, assets, supplied):
        ready = clock()
        def infer(prepared, region, bound, stages, *, selected_evidence):
            record["prepared"] = elapsed(ready)
            stage = clock()
            context = prepare_context(prepared, region, bound, archived)
            record["reconstruction"] = elapsed(stage)
            record["matched"] = compare(context)
            return dict(status="nomination_slice", reason=None, arms={a: dict(latlon=None) for a in ("c0", "fitted_c")})
        with exact_ports(bound, req, audit), patch.object(v5_core, "infer", infer):
            return ordinary(document, reader, assets, supplied)

    try:
        with patch.object(algo08_position, "solve", observe):
            solve(publication, spec, native, archive, offer)
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write(output, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
