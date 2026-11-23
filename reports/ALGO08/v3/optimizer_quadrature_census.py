"""Observe charged original position trials before implementing a quadrature model."""

import argparse
from collections import Counter
from contextlib import ExitStack
from functools import wraps
import math
from pathlib import Path
import sys
from time import process_time_ns
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, solve, write
from cold_track_row_transfer import GEOGRAPHIC, dense_inputs, small_inputs
from dense_geographic_trial import host

HERE = Path(__file__).resolve().parent
REGIONAL = Path("/var/tmp/leo-regional-track.O238AD0C/scores.so")
GATE_NS = 500_000_000


def site(frame):
    """Recognize the installed secant and its existing paused variant."""
    in_linearize = False
    while frame is not None:
        name = frame.f_code.co_name
        if frame.f_code.co_filename.endswith("/compact_cavity_optimizer.py"):
            if name == "linearize":
                in_linearize = True
            if name == "bounded_secant":
                variables = frame.f_locals
                if in_linearize:
                    return (id(frame), "derivative", variables["refreshes"]+1, None)
                if "r" not in variables:
                    return (id(frame), "start", 0, None)
                return (id(frame), "trust", variables["refreshes"], float(variables["score"]))
        frame = frame.f_back
    return None


class Census:
    def __init__(self):
        self.stage = "ordinary"
        self.fits, self.rows = [], []
        self.fit_ids = {}
        self.active = None

    def stage_wrap(self, call, name):
        @wraps(call)
        def run(*args, **kwargs):
            previous, self.stage = self.stage, name
            try:
                return call(*args, **kwargs)
            finally:
                self.stage = previous
        return run

    def residual(self, call, eligible, epsilon):
        @wraps(call)
        def run(problem, x, *args, **kwargs):
            current = site(sys._getframe(1))
            if current is None:
                return call(problem, x, *args, **kwargs)
            frame_id, role, refresh, score = current
            if role == "start":
                ident = self.fit_ids[frame_id] = len(self.fits)
                self.fits.append(dict(stage=self.stage, arm="fitted_c" if problem.fitted_c else "c0",
                                      curved_rows=int(problem.keep.sum()), temporal_eligible=eligible(problem),
                                      predictive=bool(getattr(problem, "linear_entries", ()))))
            else:
                ident = self.fit_ids[frame_id]
            if self.active is not None:
                raise ValueError("Nested position trial cannot be priced twice")
            record = self.active = Counter(fit=ident, role=role, refresh=refresh)
            start = process_time_ns()
            try:
                result = call(problem, x, *args, **kwargs)
                record["cpu_ns"] = process_time_ns()-start
                if role == "trust":
                    value = float(result @ result)
                    record["accepted"] = value < score-epsilon
                    record["exact_score"] = value if math.isfinite(value) else None
                self.rows.append(dict(record))
                return result
            finally:
                self.active = None
        return run

    def geometry(self, call, label):
        @wraps(call)
        def run(*args, **kwargs):
            record = self.active
            if record is None:
                return call(*args, **kwargs)
            start = process_time_ns()
            value = call(*args, **kwargs)
            record[label+"_ns"] += process_time_ns()-start
            record[label+"_calls"] += 1
            return value
        return run


def stats(rows):
    return dict(calls=len(rows), cpu_ns=sum(row["cpu_ns"] for row in rows),
                curved_ns=sum(row.get("curved_ns", 0) for row in rows),
                predictive_ns=sum(row.get("predictive_ns", 0) for row in rows),
                curved_calculations=sum(row.get("curved_calls", 0) for row in rows),
                predictive_calculations=sum(row.get("predictive_calls", 0) for row in rows))


def attribution(rows, fits):
    if len(fits) != sum(row["role"] == "start" for row in rows):
        raise ValueError("Incomplete optimizer start coverage")
    last = {}
    good = set()
    for row in rows:
        key = row["fit"], row["refresh"]
        if row["role"] == "derivative":
            last[key[0]] = max(last.get(key[0], 0), key[1])
        if row.get("accepted"):
            good.add(key)
    groups = {}
    for stage in ("cold", "ordinary", "signed", "post_cold"):
        by_arm = {}
        for arm in ("c0", "fitted_c"):
            selected = [r for r in rows if (fits[r["fit"]]["stage"] == stage
                         or (stage == "post_cold" and fits[r["fit"]]["stage"] != "cold"))
                        and fits[r["fit"]]["arm"] == arm]
            derivative = [r for r in selected if r["role"] == "derivative"]
            if any(sum(r["fit"] == fit and r["refresh"] == refresh for r in derivative) != 2
                   for fit, refresh in {(r["fit"], r["refresh"]) for r in derivative}):
                raise ValueError("Missing an original two-column refresh")
            eligible = [r for r in derivative if r["refresh"] < last[r["fit"]]
                        and (r["fit"], r["refresh"]) in good]
            by_arm[arm] = dict(
                starting=stats([r for r in selected if r["role"] == "start"]),
                derivative=stats(derivative),
                final_derivative=stats([r for r in derivative if r["refresh"] == last[r["fit"]]]),
                trust_accepted=stats([r for r in selected if r.get("accepted")]),
                trust_rejected=stats([r for r in selected if r["role"] == "trust" and not r["accepted"]]),
                removable=stats(eligible),
                temporal_eligible=stats([r for r in eligible if fits[r["fit"]]["temporal_eligible"]]),
            )
        groups[stage] = by_arm
    return groups


def run(case, output):
    from hashlib import sha256

    machine = host()
    publication, specification = configuration()
    import cold_finalist_race
    import lighter_joint_estimator
    from cold_track_row_entry import cold_track_rows
    from early_region import before_fit
    from full_short_run import geographic_projection
    from grid_phase_state_reuse import cached_predictive_grid
    from joint_publication import full_catalogue_route
    from leo.analysis.localization_v3 import event_position, marginal, position, retained_position
    from optimized_grid import reduced_grid
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import compact_cavity_optimizer as optimizer, v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    chosen, control = dense_inputs(GEOGRAPHIC) if case == "dense" else small_inputs("physical")
    _, archive, _, packet, pin, offer = chosen
    archive_path = Path(archive["root"])
    native = read(packet)
    if sha256(packet.read_bytes()).hexdigest() != pin.removeprefix("sha256:") or archive_identity(archive_path) != archive:
        raise ValueError("The original saved launch inputs changed")

    observed = Census()
    attempts, regional, owner_roles = [], [], {}
    original, prepare = algo08_position.solve, algo08_position.prepare_packet

    def temporal_eligible(problem):
        return (type(problem) in (position.NormalPosition, retained_position.PositionNormal)
                and "calculate" not in vars(problem) and not getattr(problem, "scale_labels", ())
                and problem.keep.sum() >= 256)

    def capture(*args, **kwargs):
        packet = prepare(*args, **kwargs)
        if owner_roles:
            raise ValueError("Unexpected second selection")
        owner_roles.update({arm: [[row[k] for k in ("observation_id", "norad", "role")] for row in rows]
                            for arm, rows in packet["rows"].items()})
        return packet

    def scoped(document, reader, assets, region):
        if document is not native or reader.root != archive_path or region.document() != offer:
            raise ValueError("Saved publication inputs changed")
        with ExitStack() as stack:
            stack.enter_context(cold_track_rows())
            stack.enter_context(geographic_projection(GEOGRAPHIC, REGIONAL))
            live, _, _ = stack.enter_context(handoff(reader))
            stack.enter_context(reduced_grid())
            stack.enter_context(cached_predictive_grid())
            stack.enter_context(patch.object(event_position, "geometry_features",
                observed.geometry(event_position.geometry_features, "predictive")))
            route = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
            guarded = before_fit(route, reader, regional_bound_guard.causal_probes, regional, live.match)
            stack.enter_context(patch.object(v5_core, "infer", guarded))
            return original(document, reader, assets, region)

    # The installed curved design compiles a private copy of the geometry
    # binding when the saved publication starts.
    with ExitStack() as stack:
        for module, key, wrapper in (
            (algo08_position, "solve", scoped),
            (algo08_position, "prepare_packet", capture),
            (cold_finalist_race, "refine", observed.stage_wrap(cold_finalist_race.refine, "cold")),
            (lighter_joint_estimator, "update", observed.stage_wrap(lighter_joint_estimator.update, "signed")),
            (position.NormalPosition, "residual", observed.residual(position.NormalPosition.residual,
                                                                  temporal_eligible, optimizer.MIN_DECREASE)),
            (marginal, "_phase_geometry", observed.geometry(marginal._phase_geometry, "curved")),
        ):
            stack.enter_context(patch.object(module, key, wrapper))
        result = solve(publication, specification, native, archive_path, offer)
    checks = dict(fix=result["status"] == "ok", same_roles=owner_roles == control["selected_rows"],
                  two_arms=set(result["arms"]) == {"c0", "fitted_c"}, grid=result["grid_points"] == 179,
                  replay=all(v == 0 for v in result["objective_replay"].values()),
                  inference=len(attempts) == len(regional) == 1)
    if case == "dense":
        checks["exact_archived"] = all(result[k] == control[k] for k in ("arms", "science", "owners"))
    else:
        from leo.contracts.digests import canonical_digest
        from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
        store = FastStandardAnalysisStore(Path("/var/tmp/leo-short-graph-20261123-physical"))
        ident = control["receipt"]["run_id"]
        archived = {kind: canonical_digest({k: v for k, v in stored(ident).items()
                                           if k not in ("binding", "elapsed_seconds")})
                    for kind, stored in (("path", store.position_path), ("grid", store.position_grid))}
        checks["exact_archived"] = result["science"] == archived
    totals = attribution(observed.rows, observed.fits)
    eligible = sum(arm["removable"]["cpu_ns"] for arm in totals["post_cold"].values())
    write(output, dict(case=case, method="original_secant_observer", host=machine, input_sha256=pin,
        checks=checks, arms=result["arms"], solver_cpu_s=result["cpu_s"], solver_elapsed_s=result["elapsed_s"],
        order_digest=result["science"], owner_hashes=result["owners"], diagnostics=totals,
        rows=observed.rows, fits=observed.fits, bound_ns=eligible, gate_ns=GATE_NS, proceed=eligible >= GATE_NS,
        sources={str(p): sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__).resolve(), HERE / "optimizer-quadrature-protocol.md", Path(optimizer.__file__),
        )}))
    if not observed.fits or not all(checks.values()):
        raise ValueError(f"Incomplete observer or failed scientific reference: {checks}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=("dense", "weak"))
    cli.add_argument("output", type=Path)
    run(**vars(cli.parse_args()))
