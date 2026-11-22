"""Time and audit candidate cross-arm projection reuse without changing the grid."""

import argparse
import os
import runpy
import subprocess
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch

import numpy as np


SOURCE = Path(__file__).resolve()
HELPER = SOURCE.with_name("residual_attribution_trial.py")
PREVIOUS = SOURCE.with_name("solver_fused_phase_trial.py")
SPEC = "sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423"
ARMS = ("c0", "fitted_c")
SHIFTS = ("nominal", "plus", "minus")
GATE_S = .25


def row_keys(*arrays):
    count = len(arrays[0])
    rows = np.ascontiguousarray(np.column_stack([array.reshape(count, -1) for array in arrays]))
    return rows.view(f"V{rows.shape[1] * rows.dtype.itemsize}").ravel()


def matches(first, second):
    return int(np.count_nonzero(np.isin(second, np.concatenate(first)))) if first else 0


def prepared_keys(problem):
    from leo.analysis.research.continuous_curve_fit import paired_phase_states
    from leo.analysis.research.prepared_phase_geometry import prepare_phase_geometry

    center = prepare_phase_geometry(problem.sky, problem.mode_bank, problem.flat_times,
                                    problem.flat_labels, problem.reference)
    states = [paired_phase_states(problem.sky, problem.flat_times, problem.flat_labels,
                                  problem.reference + offset) for offset in (.01, -.01)]
    states.insert(0, (center.position_km, center.velocity_km_s))
    rows = {name: dict(position=row_keys(position), state=row_keys(position, velocity))
            for name, (position, velocity) in zip(SHIFTS, states, strict=True)}
    rows["mode"] = row_keys(center.position_km, center.velocity_km_s,
                            center.mode_position_km, center.mode_velocity_km_s)
    return rows


def overlap(context):
    from leo.analysis.localization_v3.predictive_linear import linear_geometry

    curved = [context["problems"][arm][0] for arm in ARMS]
    problems = {arm: {"curved": p} for arm, p in zip(ARMS, curved, strict=True)}
    if context["entries"]:
        for arm in ARMS:
            problems[arm]["predictive"] = linear_geometry(problems[arm]["curved"], context["entries"])[0]
    raw = {arm: {name: prepared_keys(p) for name, p in pair.items()} for arm, pair in problems.items()}
    first, second = (raw[arm] for arm in ARMS)
    # Cross-role and cross-shift hits also count. They would be reusable at the
    # same observer even when a row arrives at another index or phase offset.
    positions = [p[shift]["position"] for p in first.values() for shift in SHIFTS]
    states = [p[shift]["state"] for p in first.values() for shift in SHIFTS]
    modes = [p["mode"] for p in first.values()]
    statistics = {}
    for kind, values in second.items():
        a, b = (problems[arm][kind] for arm in ARMS)
        aligned = (a.flat_times.tobytes() == b.flat_times.tobytes()
                   and list(a.labels) == list(b.labels)
                   and a.flat_labels.tobytes() == b.flat_labels.tobytes())
        record = dict(rows=len(b.flat_times), aligned_times_and_labels=aligned,
                      phase_reference_rows_equal=int(np.count_nonzero(
                          a.reference[a.flat_labels].view(np.uint64)
                          == b.reference[b.flat_labels].view(np.uint64))) if aligned else None,
                      mode_rows_equal=matches(modes, values["mode"]))
        for shift in SHIFTS:
            record[shift] = dict(position_rows_equal=matches(positions, values[shift]["position"]),
                                 state_rows_equal=matches(states, values[shift]["state"]))
        statistics[kind] = record
    a, b = curved
    return dict(geometry=statistics, same_curved_mask=a.keep.tobytes() == b.keep.tobytes(),
                same_orbital_support=list(a.supported) == list(b.supported),
                same_owner_choices=[(r["component"], r["candidate_index"]) for r in a.rows]
                == [(r["component"], r["candidate_index"]) for r in b.rows]
                and list(a.alias) == list(b.alias),
                calibration_widths=[p.hardware.shape[1] for p in curved],
                fitted_column_active_rows=int(np.count_nonzero(b.hardware[b.keep, -1])))


def ceiling(timing, geometry):
    # Count the *entire* timed block for any nonzero row overlap. This gives a
    # generous bound without assuming projection cost scales with row count.
    shared = {key: value for key, value in timing.items() if "observer_cpu_ns" in key}
    for kind, rows in geometry.items():
        key = f"{kind}_fitted_c_mode_cpu_ns"
        if rows["mode_rows_equal"]:
            shared[key] = timing.get(key, 0)
        for shift in SHIFTS:
            key = f"{kind}_fitted_c_{shift}_look_cpu_ns"
            # Position identity alone could share ranges and the angular projection.
            if rows[shift]["position_rows_equal"]:
                shared[key] = timing.get(key, 0)
    return dict(gross_cpu_s=sum(shared.values()) / 1e9, timed_parts=shared)


def validate_clock_coverage(totals, geometry):
    for kind in geometry:
        for arm in ARMS:
            name = f"{kind}_{arm}"
            calls = totals[f"{name}_geometry_calls"]
            projected = [totals[f"{name}_{shift}_look_calls"] for shift in SHIFTS]
            projected.append(totals[f"{name}_mode_calls"])
            if not calls or any(count != calls for count in projected):
                raise ValueError(f"Incomplete measured projection coverage for {name}")


def worker(native, spec, archive, offer, output):
    from tools.pipeline_eval.qualification import experimental_publication

    helper = runpy.run_path(str(HELPER))
    frozen = experimental_publication.run
    measured = {}

    def audit_run(args, spec):
        from leo.analysis.localization_v3 import event_position, marginal
        from leo.analysis.localization_v3.region import SearchRegion
        from leo.analysis.research import continuous_curve_fit, orbit_uncertainty, prepared_phase_geometry
        from leo.presentation import localization_v3
        from tools import algo08_position

        sample, packet = localization_v3.sample_position_grid, algo08_position.prepare_packet
        totals, weights = Counter(), Counter()
        arm = kind = selected = None
        shift = 0
        last = None

        def prepare(context, *args, **kwargs):
            nonlocal selected
            selected = context
            return packet(context, *args, **kwargs)

        def grid(score, *args, **kwargs):
            def check(calibration, point):
                nonlocal arm, last
                arm = calibration
                try:
                    result = score(calibration, point)
                finally:
                    arm = None
                # The selected model already caches complete calculations at
                # the same coordinates. Read back its actual robust weights.
                p = selected["problems"][calibration][0]
                c = p.calculate(np.asarray(point))
                current = c["noise_precision"].view(np.uint64)
                if calibration == "c0":
                    last = point, current
                elif last is not None and last[0] == point:
                    weights["pairs"] += 1
                    if current.shape == last[1].shape:
                        mask = current == last[1]
                        used = (current != 0) | (last[1] != 0)
                        weights["slots"] += len(mask)
                        weights["equal_slots"] += int(mask.sum())
                        weights["equal_vectors"] += int(mask.all())
                        weights["active_slots"] += int(used.sum())
                        weights["equal_active_slots"] += int((mask & used).sum())
                    else:
                        weights["unequal_width_pairs"] += 1
                    last = None
                return result

            start = process_time_ns()
            try:
                return sample(check, *args, **kwargs)
            finally:
                totals["instrumented_grid_cpu_ns"] += process_time_ns() - start

        def geometry(operation, name):
            def audited(*args, **kwargs):
                nonlocal kind, shift
                if arm is None:
                    return operation(*args, **kwargs)
                kind, shift = name, 0
                start = process_time_ns()
                try:
                    return operation(*args, **kwargs)
                finally:
                    totals[f"{name}_{arm}_geometry_cpu_ns"] += process_time_ns() - start
                    totals[f"{name}_{arm}_geometry_calls"] += 1
                    kind = None
            return audited

        def clock(operation, role):
            def timed(*args, **kwargs):
                nonlocal shift
                if arm is None or (kind is None and role != "observer"):
                    return operation(*args, **kwargs)
                suffix = role
                if role == "look":
                    suffix = f"{SHIFTS[shift]}_look"
                    shift += 1
                label = f"{kind}_{arm}_{suffix}"
                start = process_time_ns()
                try:
                    return operation(*args, **kwargs)
                finally:
                    totals[f"{label}_cpu_ns"] += process_time_ns() - start
                    totals[f"{label}_calls"] += 1
            return timed

        targets = ((continuous_curve_fit, "geodetic_to_ecef_km", "observer"),
                   (continuous_curve_fit, "ecef_to_enu_matrix", "observer"),
                   (orbit_uncertainty, "geodetic_to_ecef_km", "observer"),
                   (SearchRegion, "latlon", "observer"),
                   (continuous_curve_fit, "look_angles", "look"),
                   (orbit_uncertainty, "frequency_modes_from_states", "mode"),
                   (prepared_phase_geometry, "frequency_modes_from_states", "mode"))
        with ExitStack() as patches:
            for module, name, role in targets:
                patches.enter_context(patch.object(module, name, clock(getattr(module, name), role)))
            patches.enter_context(patch.object(marginal, "_phase_geometry",
                                                geometry(marginal._phase_geometry, "curved")))
            patches.enter_context(patch.object(event_position, "geometry_features",
                                                geometry(event_position.geometry_features, "predictive")))
            patches.enter_context(patch.object(algo08_position, "prepare_packet", prepare))
            patches.enter_context(patch.object(localization_v3, "sample_position_grid", grid))
            result = frozen(args, spec)
        report = overlap(selected)
        validate_clock_coverage(totals, report["geometry"])
        measured.update(report, timing=totals, weights=weights, ceiling=ceiling(totals, report["geometry"]))
        return result

    with TemporaryDirectory() as directory:
        path = Path(directory) / "stock.json"
        with patch.object(experimental_publication, "run", audit_run):
            helper["worker"](native, spec, archive, offer, path, include_evidence=True)
        result = helper["read"](path)
    helper["write"](output, dict(result, audit=measured))


def run(pair, frozen, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    previous = runpy.run_path(str(PREVIOUS))
    helper = runpy.run_path(str(HELPER))
    read, write = helper["read"], helper["write"]
    original_pair, original, spec, archive, offer, native = previous["saved_inputs"](
        pair, frozen, None, expected_spec=SPEC)
    release = helper["RELEASE"]
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{release / 'src'}:{release}", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    command = [str(release / "venv/bin/python"), "-BPs", str(SOURCE), "worker"]
    with TemporaryDirectory() as directory:
        folder = Path(directory)
        observations, region, receipt = (folder / name for name in ("native.json", "offer.json", "result.json"))
        write(observations, native)
        write(region, offer)
        subprocess.run([*command, *map(str, (observations, spec, archive, region, receipt))],
                       env=env, check=True, timeout=88)
        result = read(receipt)
    if archive_identity(archive) != original_pair["archive"]:
        raise ValueError("Causal archive changed during audit")
    science = result.pop("evidence")
    digests = {key: canonical_digest({k: v for k, v in value.items()
                                      if k not in ("binding", "elapsed_seconds")})
               for key, value in science.items()}
    checks = dict(arms=result["arms"] == original["arms"], owners=result["owners"] == original["owners"],
                  grid=digests["position_grid"] == original["scientific_digests"]["grid"],
                  path=digests["position_path"] == original["scientific_digests"]["path"],
                  status=result["status"] == "ok", grid_complete=science["position_grid"]["complete"])
    write(output, dict(specification_sha256=SPEC, pair_sha256=sha256(pair.read_bytes()).hexdigest(),
                       native_sha256=canonical_digest(native), archive=original_pair["archive"], offer=offer,
                       result=result, digests=digests, original_checks=checks, threshold_s=GATE_S,
                       grid_points=science["position_grid"]["evaluated_points"]))
    if not all(checks.values()):
        raise ValueError(f"Audit replay did not reproduce the frozen publication. See {output}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    trial, child = commands.add_parser("run"), commands.add_parser("worker")
    for name in ("pair", "frozen", "output"):
        trial.add_argument(name, type=Path)
    for name in ("native", "spec", "archive", "offer", "output"):
        child.add_argument(name, type=Path)
    values = vars(cli.parse_args())
    {"run": run, "worker": worker}[values.pop("action")](**values)
