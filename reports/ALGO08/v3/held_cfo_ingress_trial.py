"""Verify and profile the two complete CFO feature paths on identical admitted inputs."""

import argparse
from gzip import decompress
import json
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

from leo.analysis.localization_v3.tracks import winning_observations
from leo.analysis.polynomial_tracklets import TrackConfig

from . import held_cfo_features as frozen
from . import held_cfo_ingress as ingress
from .held_cfo_features_trial import (
    BASELINE_PIN, CASES, CONFIG, CONFIG_PIN, PLAN, PLAN_PIN, canonical, checked_bytes, clock, proof,
)


def run(case, order):
    start = perf_counter(), process_time()
    config = TrackConfig(**json.loads(checked_bytes(CONFIG, CONFIG_PIN))["config"])
    original_path, original_pin, history_path, history_pin = CASES[case]
    native = json.loads(checked_bytes(Path(original_path), original_pin))
    native_before = canonical(native)
    input_cost = clock(start)
    start = perf_counter(), process_time()
    winners, metadata = winning_observations(native)
    common_cost = clock(start)
    rows, sidecars, overlays = {}, {}, {}
    for key in order:
        before = getrusage(RUSAGE_SELF)
        start = perf_counter(), process_time()
        features = frozen.derive(native, config) if key == "A" else ingress.derive(native, config, winners)
        corrected = frozen.apply_to_winners(native, winners, features)
        cost = clock(start)
        after = getrusage(RUSAGE_SELF)
        rows[key] = dict(**cost, minor_faults=after.ru_minflt-before.ru_minflt,
                         major_faults=after.ru_majflt-before.ru_majflt,
                         input_blocks=after.ru_inblock-before.ru_inblock, maxrss_kib=after.ru_maxrss)
        sidecars[key], overlays[key] = features, corrected

    start = perf_counter(), process_time()
    expected = json.loads(decompress(checked_bytes(PLAN, PLAN_PIN)))
    prior_winners, _ = winning_observations(json.loads(checked_bytes(Path(history_path), history_pin)))
    registered = expected["cases"][case]
    first = sidecars["A"]
    if (expected["pins"]["archived_predictions"] != BASELINE_PIN or
            registered["native_sha256"] != "sha256:" + original_pin or
            first.edits != registered["eligible"] or first.forecasts != registered["forecasts"] or
            first.gates != registered["residual_gates"] or first.eligibility != registered["graph_forecast_eligibility"] or
            any(registered["graph"][name] != value for name, value in first.masked_graph.items()) or
            sidecars["B"] != first or overlays["A"] != prior_winners or overlays["B"] != prior_winners or
            canonical(native) != native_before or metadata["detector_sha256"] != first.native_identity[-1]):
        raise ValueError("CFO ingress mismatch against the frozen pipeline or historical worker")
    row_pin = canonical(prior_winners)
    sidecar_pin = canonical(vars(first))
    verification_cost = clock(start)
    return dict(case=case, order=order, feature=rows, source_checks_and_decoding=input_cost,
                ordinary_winning_extraction=common_cost, independent_readback=verification_cost,
                released_consumed_rows_sha256=row_pin, frozen_sidecar_sha256=sidecar_pin,
                edits=len(first.edits), original_winners=len(winners), masked_graph=first.masked_graph,
                original_native_sha256=original_pin, original_config_sha256=CONFIG_PIN,
                historical_plan_sha256=PLAN_PIN, historical_variant_sha256=history_pin, evidence_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    jobs = tuple(f"{case}:{order}" for case in CASES for order in ("AB", "BA"))
    parser.add_argument("job", choices=(*jobs, "proof"))
    parser.add_argument("--isolated", action="store_true")
    args = parser.parse_args()
    evidence = proof() if args.isolated else None
    if args.job == "proof":
        if evidence is None:
            parser.error("Kernel proof needs the isolated worker")
        result = evidence | {"ingress_imports_from": str(Path(ingress.__file__))}
    else:
        if evidence is not None and (evidence["cpu"] != [2] or evidence["nice"] != 15):
            raise ValueError("Timed child requires the authorized low-priority CPU2 slot")
        result = run(*args.job.split(":")) | {"isolation": evidence}
    result["python_cpu_through_readback_s"] = process_time()
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
