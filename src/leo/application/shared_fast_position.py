"""Bounded, source-independent shared-q positioning from public tracking evidence.

The production initializer is a named adaptation, not the DS21/DS22 saved-source
recipe. The shared final likelihood is exact. No station reference is accepted.
"""

import time
from dataclasses import asdict, replace

import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.channel_group_seeds import shared_bootstrap_seed
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.analysis.regional_position_score import ALIAS_HZ, coordinates
from leo.analysis.research.doppler_shape_orbits import DopplerShapeOrbitObjective, fit_doppler_shape
from leo.analysis.research.doppler_shape_shared_proposals import (
    decode_physical_correction,
    encode_initial_physical_seed,
)
from leo.analysis.sequential_group_calibration import fit_sequential_path
from leo.analysis.shared_scan_model import (
    MODEL_VERSION,
    SharedScanObjective,
    bounded_fit,
    donor_state,
)
from leo.application.channel_group_discovery import DiscoverySliceExpired, discover_channel_groups
from leo.application.channel_group_refinement import objective
from leo.application.regional_position_inputs import (
    PositionInputUnavailable,
    prepare_position_windows,
)

SOURCE_POLICY = "generic-cold24-shape3-fresh-six-ab-v1"
POLICY = dict(
    model_version=MODEL_VERSION,
    source_generation_policy=SOURCE_POLICY,
    discovery_points=24,
    discovery_seconds=240,
    discovery_levels_km=[100.0, 50.0, 25.0, 12.5],
    shape_starts_per_view=1,
    shape_seconds=20,
    bootstrap_seconds=5,
    source_starts=6,
    maximum_source_optimizer_calls=24,
    maximum_shared_optimizer_calls=2,
    final_shared_reserve_seconds=40,
    local_radius_km=25.0,
    fitted_c=True,
    fit_seconds=20,
    solver_seconds=15,
    audit_reserve_seconds=5,
    actual_objectives_per_fit=2000,
    iterations=600,
    visibility_width=1e-5,
    source_selector="full-zero-q A minimum J plus genuine joint B minimum J",
    reference_usage="none",
    held_usage="none",
    development_metric_transfer=False,
)


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def supported_sequences(obs, tracks):
    """Original disjoint lane/alias/gap shape support, without invented tracks."""
    sequences, used = [], set()
    for track in tracks:
        chunk = []
        for row in sorted(set(track), key=lambda r: (obs.times_s[r], obs.window_ids[r])):
            previous = chunk[-1] if chunk else None
            broken = previous is not None and (
                obs.times_s[row] - obs.times_s[previous] > 4
                or obs.receiver[row] != obs.receiver[previous]
                or obs.channel[row] != obs.channel[previous]
                or obs.rf_hz[row] != obs.rf_hz[previous]
                or abs(obs.measured_hz[row] - obs.measured_hz[previous]) > ALIAS_HZ / 2
            )
            if row in used or broken:
                if len(chunk) >= 2:
                    sequences.append(tuple(chunk))
                    used.update(chunk)
                chunk = []
            if row not in used:
                chunk.append(row)
        if len(chunk) >= 2:
            sequences.append(tuple(chunk))
            used.update(chunk)
    return tuple(sequences)


def discovery_selection(rows):
    """Finalize only completed points if the finite discovery slice expires."""
    ranked = []
    for view in ("low", "high", "all"):
        eligible = [r for r in rows if r["fits"].get(view, {}).get("converged")]
        if eligible:
            ranked.append(
                min(
                    eligible,
                    key=lambda r: (r["fits"][view]["objective"], r["east_km"], r["north_km"]),
                )
            )
    ranked.extend(
        sorted(
            (r for r in rows if r["selection_score"] < 1e100),
            key=lambda r: (r["selection_score"], r["east_km"], r["north_km"]),
        )
    )
    selected = []
    for row in ranked:
        point = np.array([row["east_km"], row["north_km"]])
        if all(
            np.linalg.norm(point - [other["east_km"], other["north_km"]]) >= 12.5
            for other in selected
        ):
            selected.append(row)
        if len(selected) == 3:
            break
    return selected


def prepare_views(source):
    """Full available scan is inference data; no pretend development holdout."""
    result = {}
    for view, channels in (("all", range(1, 9)), ("low", range(1, 5)), ("high", range(5, 9))):
        selected = replace(source, probes=tuple(p for p in source.probes if p.channel in channels))
        result[view] = prepare_position_windows(selected)
    obs = result["all"].observations
    nodes = np.arange(
        np.floor(obs.times_s.min() / 30) * 30, np.ceil(obs.times_s.max() / 30) * 30 + 1, 30.0
    )
    if len(nodes) < 3:
        raise PositionInputUnavailable("At least three30s common-clock nodes required")
    return result, nodes


def sequential_source(*args, **kwargs):
    """A capped final has no physical function; isolate that path, never invent one."""
    try:
        return fit_sequential_path(*args, **kwargs)
    except (ValueError, KeyError) as error:
        return dict(status="unavailable", reason=str(error), error_type=type(error).__name__)


def run_shared_position(
    source, prepared, full_bank, prior, nodes, receipts, *, maximum_seconds=960.0
):
    """Generate every source freshly, then fit two exact shared-q initializers.

    receipts exposes immutable get/put(name,payload); returned nonstationary
    stages remain durable failures. This operation never retries a prior launch.
    """
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1200:
        raise ValueError("Bounded shared inference allowance<=1200s required")
    begun = time.monotonic()
    invocations = []

    def reserve(seconds, final=False):
        if time.monotonic() - begun + seconds + (0 if final else 40) >= maximum_seconds:
            raise TimeoutError("Insufficient whole-scan stage reserve")

    def stage(name, seconds, operation):
        reserve(seconds, final=name.startswith("shared-all-"))
        if receipts.get(name + "-launch") is not None:
            raise ValueError("Previously attempted shared stage; no automatic retry")
        receipts.put(name + "-launch", dict(stage=name, reserve_seconds=seconds))
        start = time.monotonic()
        try:
            result = operation()
        except (ValueError, TimeoutError) as error:
            result = dict(unavailable=True, reason=str(error), error_type=type(error).__name__)
        receipts.put(name, plain(dict(result=result, elapsed_seconds=time.monotonic() - start)))
        return result

    class Points:
        def __init__(self):
            self.rows = {}

        def get(self, key):
            return self.rows.get(key)

        def put(self, key, value):
            receipts.put("discovery-" + key, plain(value))
            self.rows[key] = value

    points = Points()

    def discover():
        try:
            value = discover_channel_groups(
                prepared,
                full_bank,
                prior,
                points,
                maximum_seconds=240,
                points=24,
                clock_nodes=nodes,
                levels_km=tuple(POLICY["discovery_levels_km"]),
            )
        except DiscoverySliceExpired as error:
            selected = discovery_selection(list(points.rows.values()))
            value = dict(
                selected=selected,
                available=len(selected) == 3,
                points=len(points.rows),
                stop_reason=str(error),
            )
        return value

    discovery = stage("discovery", 240, discover)
    if not discovery.get("available"):
        raise PositionInputUnavailable("Three supported discovery basins unavailable")
    cold = discovery["selected"]
    initial_indices = sorted(
        {i for r in points.rows.values() for i in r["satellite_indices"]},
        key=lambda i: full_bank.numbers[i],
    )
    initial_bank = full_bank.select(initial_indices)
    centers = [[r["east_km"], r["north_km"]] for r in cold]
    # One training-only cold winner per view, explicitly different from research
    # three-start shape searches. Missing shape support remains an unavailable path.
    for view in ("low", "high", "all"):
        p = prepared[view]
        sequences = supported_sequences(p.observations, p.bootstrap_tracks)
        eligible = [r for r in cold if r["fits"].get(view, {}).get("converged")]
        if not sequences or not eligible:
            centers.append(None)
            receipts.put("shape-" + view, dict(unavailable=True, reason="no supported shape start"))
            continue
        start = min(eligible, key=lambda r: r["fits"][view]["objective"])
        result = stage(
            "shape-" + view,
            20,
            lambda p=p, sequences=sequences, start=start: fit_doppler_shape(
                DopplerShapeOrbitObjective(p.observations, initial_bank, prior, sequences),
                [[start["east_km"], start["north_km"]]],
                rf_arm="fitted-c",
                maximum_seconds=20,
                maximum_iterations=600,
            ),
        )
        winner = result.get("winner")
        centers.append(None if winner is None else winner["theta"][:2])
    hypotheses = []
    for index, center in enumerate(centers):
        views = {}
        if center is not None:
            for view, p in prepared.items():
                result = stage(
                    f"bootstrap-{index}-{view}",
                    5,
                    lambda p=p, center=center: asdict(
                        bootstrap_position(
                            p.observations,
                            full_bank,
                            prior,
                            center,
                            p.bootstrap_tracks,
                            maximum_seconds=5,
                            orbit_predictor=predict_orbits,
                        )
                    ),
                )
                if not result.get("unavailable"):
                    from leo.analysis.regional_position_bootstrap import PositionBootstrap

                    views[view] = (
                        PositionBootstrap(
                            tuple(result["satellite_indices"]), np.asarray(result["vector"]), ()
                        ),
                        p.observations,
                    )
        hypotheses.append(views)
    indices = sorted(
        {i for views in hypotheses for b, _ in views.values() for i in b.satellite_indices},
        key=lambda i: full_bank.numbers[i],
    )
    if not indices:
        raise PositionInputUnavailable("No bootstrap-supported candidate union")
    bank = full_bank.select(indices)
    receipts.put("candidate-union", dict(numbers=bank.numbers.tolist(), indices=indices))
    fallback = {}
    for views in hypotheses:
        for b, _ in views.values():
            from leo.analysis.regional_position_score import zero_sum_basis

            times = b.vector[7] + zero_sum_basis(len(b.satellite_indices)) @ b.vector[8:]
            for i, shift in zip(b.satellite_indices, times, strict=True):
                fallback.setdefault(i, float(shift))
    models = {v: objective(p, bank, prior, nodes) for v, p in prepared.items()}
    low = GroupCalibrationObjective(
        models["low"].base, models["low"].observations.channel >= 5, enabled=False
    )
    sources, b_fits = [], []
    for index, views in enumerate(hypotheses):
        if time.monotonic() - begun + 120 >= maximum_seconds:
            receipts.put(
                f"source-{index}",
                dict(
                    unavailable=True, reason="Preserved40s final reserve; source admission closed"
                ),
            )
            continue
        if not views:
            receipts.put(f"source-{index}", dict(unavailable=True, reason="bootstrap unavailable"))
            continue
        try:
            seeds = {
                v: shared_bootstrap_seed(m, indices, views, fallback_timings=fallback)
                for v, m in models.items()
            }
        except ValueError as error:
            receipts.put(f"source-{index}", dict(unavailable=True, reason=str(error)))
            continue
        center = centers[index]
        high_seed = seeds["high"]
        correction = decode_physical_correction(
            encode_initial_physical_seed(models["high"], high_seed["vector"], high_seed["nuisance"])
        )
        accepted = {}

        def stage_fit(
            name, model, vector, nuisance, options, index=index, center=center, accepted=accepted
        ):
            row = stage(
                f"A-{index}-{name}",
                20,
                lambda: bounded_fit(
                    model, vector, nuisance, local_center=center, fixed_position=name == "high"
                ),
            )
            invocations.append(row)
            fit = row.get("fit", {})
            accepted[name] = row.get("audit", {}).get("accepted", False)
            if fit and not accepted[name]:
                fit = dict(fit, converged=False)
            return fit if fit else dict(converged=False, reason=row.get("reason", "no endpoint"))

        path = sequential_source(
            low,
            models["high"].base,
            models["all"].base,
            seeds["low"]["vector"],
            high_seed["vector"],
            seeds["all"]["vector"],
            low_nuisance=seeds["low"]["nuisance"],
            high_correction_seed=correction,
            local_center=center,
            local_radius_km=25,
            stage_fit=stage_fit,
        )
        receipts.put(f"A-{index}-path", dict(status=path["status"], accepted_stages=accepted))
        if path["status"] == "complete" and all(accepted.values()):
            sources.append(
                dict(
                    name=f"A-{index}",
                    index=index,
                    raw=path["final_model"],
                    shift=path["shift"],
                    fit=path["final"],
                    center=center,
                )
            )
        row = stage(
            f"B-{index}",
            20,
            lambda seeds=seeds, center=center: bounded_fit(
                models["all"], seeds["all"]["vector"], seeds["all"]["nuisance"], local_center=center
            ),
        )
        invocations.append(row)
        if row.get("audit", {}).get("accepted"):
            b_fits.append(dict(index=index, fit=row["fit"], center=center))
    if not sources or not b_fits:
        raise PositionInputUnavailable("Both a strict original A and joint B source are required")
    for row in sources:
        m = SharedScanObjective(row["raw"], row["shift"])
        value = stage(
            "prescreen-" + row["name"],
            1,
            lambda m=m, row=row: dict(
                objective=m.evaluate_joint(
                    row["fit"]["vector"],
                    np.r_[row["fit"]["nuisance"], np.zeros(m.observation_parameter_count)],
                )[0],
                actual_objective_calls=1,
            ),
        )
        if value.get("unavailable"):
            raise PositionInputUnavailable("Full-zero-q source prescreen unavailable")
        row["prescreen_J"] = value["objective"]
    a = min(sources, key=lambda r: (r["prescreen_J"], r["index"]))
    b = min(b_fits, key=lambda r: (r["fit"]["objective"], r["index"]))
    raw, shift, v, n, error = donor_state(models["all"], b["fit"])
    donor = dict(
        name="B-all",
        index=b["index"],
        raw=raw,
        shift=shift,
        fit=dict(vector=v, nuisance=n),
        center=b["center"],
        transport_error_hz=error,
    )
    receipts.put(
        "source-selection",
        plain(
            dict(
                A=a["name"],
                A_prescreen=[dict(source=r["name"], J=r["prescreen_J"]) for r in sources],
                B_index=b["index"],
                B_transport_error_hz=error,
            )
        ),
    )
    final = []
    for row in (a, donor):
        m = SharedScanObjective(row["raw"], row["shift"])
        call = "shared-all-" + row["name"]
        result = stage(
            call,
            20,
            lambda m=m, row=row: bounded_fit(
                m,
                row["fit"]["vector"],
                np.r_[row["fit"]["nuisance"], np.zeros(m.observation_parameter_count)],
                local_center=row["center"],
            ),
        )
        invocations.append(result)
        if result.get("audit", {}).get("accepted"):
            final.append(dict(source=row["name"], call=call, **result))
    if not final:
        raise PositionInputUnavailable("Neither shared-q endpoint passed strict admission")
    selected = min(final, key=lambda r: (r["fit"]["objective"], r["source"]))
    lat, lon = coordinates(prior, selected["fit"]["vector"][:2])
    return plain(
        dict(
            position=dict(latitude_deg=lat, longitude_deg=lon),
            selection=dict(
                accepted=True,
                source=selected["source"],
                call=selected["call"],
                objective=selected["audit"]["objective"],
                NLL=selected["audit"]["likelihood_nll"],
                stationarity=selected["audit"]["stationarity"],
            ),
            selected_fit=selected["fit"],
            candidate_numbers=bank.numbers,
            optimizer_calls=len(invocations),
            actual_objective_calls=sum(r.get("actual_objective_calls", 0) for r in invocations),
            prescreen_objective_calls=len(sources),
            elapsed_seconds=time.monotonic() - begun,
            source_generation_policy=SOURCE_POLICY,
            cost_scope=(
                "A/B/shared counted; discovery/shape/bootstrap have separate stage receipts"
            ),
        )
    )
