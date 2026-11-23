"""Price a hypothetical mixed stereo scout from measured and byte-pinned receipts."""

import argparse
import csv
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
from math import isclose


HERE = Path(__file__).resolve().parent
PINS = {
    "measurements/acquisition-split-DS30-0008.json": "b4bd3489b7b7c3477f7177ca5714f420ce2b8bf845f5c03315f3f8d8c4192421",
    "measurements/receiver-polyphase-timing.json": "fc7a810e5ce43968de08c26e1e3726a4e8dbbfb047f5d41675c1aa0a7d4deba5",
    "measurements/directed-verifier.json.gz": "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b",
    "first-55/stage-clocks.csv": "dc046009db376b6655886d73755d61a8bad5d14b2a7c99b1231ad2cfff74e2f9",
    "measurements/stereo-fft.json": "bfaacbca6e9313d13bcdac34fdb6e50b38b44ef8d023ef606acfc61878f9ac39",
}


def read(path):
    blob = (HERE / path).read_bytes()
    if sha256(blob).hexdigest() != PINS[path]:
        raise ValueError(f"Measured source changed: {path}")
    return blob


def panel(profile, stereo, oracle):
    if profile["inputs"] != stereo["inputs"] or profile["inputs"] != oracle["input_digests"]:
        raise ValueError("Stage transfer requires identical pre-existing weak or dense I/Q hashes")
    if stereo["differences"]:
        raise ValueError("Stereo callback eligibility must reproduce stock science")
    runs = profile["comparisons"]["half_grid"]["total_cpu_s"]
    timing = profile["stages"][0]["timing"]
    installed = sum(pair[0] for pair in runs)
    paths = stereo["repeats"][0]["paths"]
    primary = paths["paired_primary"]
    both_residual = paths["paired_residual"]
    singleton_residual = paths["one_residual"]
    scouts = 2 * (primary + both_residual) + singleton_residual
    if primary != stereo["visits"] or timing["calls"] != scouts * len(runs):
        raise ValueError("Independent scout counts do not match the originally profiled work")
    share = timing["cpu_s"] / installed
    return dict(
        stereo_visits=primary, paired_residuals=both_residual, singleton_residuals=singleton_residual,
        original_scouts_per_repeat=scouts, native_factor_cpu_s=installed, aggregate_timing_cpu_s=timing["cpu_s"],
        share_for_all_scouts=share, original_factors_by_rank=stereo["exact_installed_factors_by_rank"],
        no_contender_measurement=True,
        optimistic_native_reduction_if=dict(
            share_primary=share * primary / scouts,
            share_primary_and_paired_residuals=share * (primary + both_residual) / scouts,
            free_all_scouts=share,
        ),
    )


def project(outside_cpu, outside_elapsed, callbacks, cold_wall, warm, alternatives):
    cold_acq = outside_cpu + callbacks
    cold_cap = cold_acq / 2.
    cold_callback_cap = cold_cap - outside_cpu
    warm_outside = warm["launch_to_detections_s"] - callbacks
    warm_half = warm["elapsed_s"] / 2.
    publish = warm["terminal_to_exit_s"]
    caps = dict(halved_solver=warm_half - publish - warm["detections_to_terminal_s"] / 2.,
                planned_24_second_solver=warm_half - publish - 24.)
    scenarios = {}
    for name, remaining in alternatives.items():
        warm_acq = warm_outside + remaining
        scenarios[name] = dict(
            projected_remaining_native_cpu_s=remaining,
            projected_cold_acquisition_cpu_s=outside_cpu + remaining,
            misses_cold_half_cpu_by_s=outside_cpu + remaining - cold_cap,
            projected_warm_acquisition_elapsed_s=warm_acq,
            maximum_warm_solver_elapsed_s=warm_half - publish - warm_acq,
            misses_warm_acquisition_by_s={key: warm_acq - cap for key, cap in caps.items()},
        )
    return dict(
        measured_cold_cpu_s=cold_acq, measured_cold_elapsed_s=cold_wall,
        cold_native_callback_cpu_s=callbacks, cold_outside_cpu_s=outside_cpu,
        cold_outside_elapsed_s=outside_elapsed, cold_half_cpu_s=cold_cap,
        cold_callback_budget_cpu_s=cold_callback_cap,
        needed_cold_native_reduction=1. - cold_callback_cap / callbacks,
        cold_half_elapsed_s=cold_wall / 2., cold_outside_exceeds_half_elapsed_s=outside_elapsed - cold_wall / 2.,
        historical_warm=warm, estimated_warm_outside_elapsed_s=warm_outside,
        warm_acquisition_elapsed_ceiling_s=caps, alternatives=scenarios,
    )


def measure(output):
    stages = json.loads(read("measurements/receiver-polyphase-timing.json"))["runs"]
    stereo = json.loads(read("measurements/stereo-fft.json"))["cohorts"]
    directed = json.loads(gzip.decompress(read("measurements/directed-verifier.json.gz")))["groups"]
    cold = json.loads(read("measurements/acquisition-split-DS30-0008.json"))
    warm, = [row for row in csv.DictReader(io.StringIO(read("first-55/stage-clocks.csv").decode()))
             if row["recording"] == "DS30-0008"]
    panels = {case: panel(stages[case], stereo[case], directed[case]) for case in ("weak", "dense")}
    warm = {key: float(value) for key, value in warm.items() if key != "recording"}
    original_groups = cold["detector_groups"].values()
    stereo_visits = sum(group["visits"] for group in original_groups)
    native = sum(group["cpu_s"] for group in original_groups)
    outside_cpu = cold["outside_detector_cpu_s"]
    if not isclose(outside_cpu + native, cold["in_process_to_solver_cpu_s"], abs_tol=1e-9):
        raise ValueError("The complete cold callback attribution changed")
    exact = directed["dense"]["checks"]["strict_decode"]
    exact_cancellation_and_verifier_ms_per_lane = sum(
        exact["mean_stages_ms"][key] for key in ("cancel", "load", "verify"))
    independent_work = dict(
        original_exact_known_positive_route_ms_per_stereo=2 * exact["cpu_ms"]["mean"],
        original_cancel_load_verify_without_confirmation_ms_per_stereo=2 * exact_cancellation_and_verifier_ms_per_lane,
    )
    remains = {name: native * (1. - possible)
               for name, possible in panels["dense"]["optimistic_native_reduction_if"].items()}
    remains.update({name: milliseconds * stereo_visits / 1000.
                    for name, milliseconds in independent_work.items()})
    budget = project(outside_cpu, cold["outside_detector_wall_s"], native, cold["in_process_to_solver_wall_s"],
                     warm, remains)
    with output.open("x") as stream:
        print(json.dumps(dict(panels=panels, complete_stereo_visits=stereo_visits, oracle_scope=independent_work,
                             budget=budget, source_pins=PINS, code_sha256=sha256(Path(__file__).read_bytes()).hexdigest()),
                         indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    measure(cli.parse_args().output)
