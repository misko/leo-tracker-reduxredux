"""Compare a guarded coarse-support orbit bank at the original regional proof port."""

from argparse import ArgumentParser
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from aperture_trial import ARMS, configuration, solve, write
from dense_geographic_trial import elapsed, host, now
from live_orbit_setup_audit import INPUT_PINS, bound_input, file_hash


STEP = 8
LIMITS = dict(position_m=0.30, velocity_m_per_s=0.035, frequency_hz=1.0,
              tangent_hz_per_s=2.0, score=0.003)
STOP = "orbit_interpolation_proof_only"


def lattice(knots):
    if len(knots) < 3 or not np.isfinite(knots).all() or not np.all(np.diff(knots) == 1):
        return None
    support = np.r_[np.arange(0, len(knots) - 1, STEP), len(knots) - 1]
    widths = np.diff(support)
    sentinel = (support[:-1] + widths // 2)[widths > 1]
    return support, sentinel, np.union1d(support, sentinel)


def hermite(support, position, velocity, times):
    """Evaluate position and its time derivative without extrapolating."""
    if (len(support) < 2 or not np.all(np.diff(support) > 0) or not np.isfinite(support).all()
            or not np.isfinite(times).all() or np.any(times < support[0]) or np.any(times > support[-1])):
        raise ValueError("Interpolation requires finite times within increasing support")
    starts = np.minimum(np.searchsorted(support, times, side="right") - 1, len(support) - 2)
    step = (support[starts + 1] - support[starts])[None, :, None]
    u = (times - support[starts])[None, :, None] / step
    p0, p1 = position[:, starts], position[:, starts + 1]
    v0, v1 = velocity[:, starts], velocity[:, starts + 1]
    movement = p1 - p0 - step * v0
    velocity_change = step * (v1 - v0)
    quadratic = 3 * movement - velocity_change
    cubic = velocity_change - 2 * movement
    p = p0 + u * (step * v0 + u * (quadratic + u * cubic))
    v = v0 + u * (2 * quadratic + 3 * u * cubic) / step
    exact = np.searchsorted(support, times)
    found = support[exact] == times
    p[:, found], v[:, found] = position[:, exact[found]], velocity[:, exact[found]]
    return p, v


def state_error(baseline, candidate):
    p0, v0, good0 = baseline
    p1, v1, good1 = candidate
    usable = good0 & good1
    return dict(position_m=1e3 * float(np.linalg.norm(p0[usable] - p1[usable], axis=-1).max(initial=0)),
                velocity_m_per_s=1e3 * float(np.linalg.norm(v0[usable] - v1[usable], axis=-1).max(initial=0)),
                usable_changes=int(np.count_nonzero(good0 != good1)))


class CoarseBank:
    """Use eight-second supports only when all midpoint sentinels agree."""

    def __init__(self, exact):
        self.exact = exact
        self.raw_approximation = None
        self.audit = {}

    def __call__(self, catalogue, origin, knots):
        def fallback(reason):
            start = process_time_ns()
            result = self.exact(catalogue, origin, knots)
            self.audit.update(fallback=reason, full_fallback_cpu_ns=process_time_ns() - start)
            return result

        start = process_time_ns()
        plan = lattice(knots)
        self.audit["support_plan_cpu_ns"] = process_time_ns() - start
        if plan is None:
            return fallback("incompatible_lattice")
        support, sentinel, paid = plan
        self.audit.update(support_indices=support.tolist(), sentinel_indices=sentinel.tolist(),
                          orbits=len(catalogue), paid_knots=len(paid), original_knots=len(knots))
        start = process_time_ns()
        p, v, good = self.exact(catalogue, origin, knots[paid])
        self.audit["sampled_sgp4_ecef_cpu_ns"] = process_time_ns() - start
        if not good.all() or not np.isfinite(p).all() or not np.isfinite(v).all():
            return fallback("unusable_sampled_orbit")
        start = process_time_ns()
        rows = np.searchsorted(paid, support)
        approx_p, approx_v = hermite(knots[support], p[:, rows], v[:, rows], knots)
        if not np.isfinite(approx_p).all() or not np.isfinite(approx_v).all():
            self.audit["interpolation_and_check_cpu_ns"] = process_time_ns() - start
            return fallback("nonfinite_interpolation")
        self.raw_approximation = approx_p, approx_v, good
        rows = np.searchsorted(paid, sentinel)
        errors = state_error((p[:, rows], v[:, rows], good), (approx_p[:, sentinel], approx_v[:, sentinel], good))
        self.audit.update(sentinel_errors=errors, interpolation_and_check_cpu_ns=process_time_ns() - start)
        if any(errors[name] > LIMITS[name] for name in ("position_m", "velocity_m_per_s")):
            return fallback("sentinel_tolerance")
        self.audit["fallback"] = None
        return self.raw_approximation


class ProofPass:
    def __init__(self, kernel, proof, projector, *, mode="exact", replay=None):
        self.kernel, self.proof, self.projector = kernel, proof, projector
        self.exact, self.replay = kernel.ecef_states, replay
        self.phase_prepare = kernel.prepare_phase_geometry
        self.mode = mode
        self.fine = CoarseBank(self.exact) if mode == "candidate" else self.exact
        self.states, self.visited = [], []
        self.clocks = {}
        self.geometry = None

    def states_at(self, catalogue, origin, knots):
        index = len(self.states)
        if index not in (0, 1):
            raise ValueError("Expected one exact horizon screen and one regular fine bank")
        name = ("horizon_screen", "fine_bank")[index]
        start = process_time_ns()
        if self.replay is None:
            operation = self.fine if index else self.exact
            result = operation(catalogue, origin, knots)
        else:
            times, labels, result = self.replay[index]
            if not np.array_equal(times, knots) or labels != tuple(catalogue.satellite_numbers):
                raise ValueError("Offline bank request changed")
        self.clocks[name + "_cpu_ns"] = process_time_ns() - start
        self.states.append((knots, tuple(catalogue.satellite_numbers), result))
        return result

    def phase(self, *args, **options):
        start = process_time_ns()
        self.geometry = self.phase_prepare(*args, **options)
        self.clocks["phase_geometry_cpu_ns"] = process_time_ns() - start
        return self.geometry

    def evaluate(self, tracks, reader, region):
        from tools.pipeline_eval.variants.experimental import regional_veto_short_circuit as short_circuit

        terminal = short_circuit.evaluate_terminal

        def record_terminal(points, width, score):
            def record(point):
                self.visited.append((point["side"], point["xy_km"]))
                return score(point)

            start = process_time_ns()
            result = terminal(points, width, record)
            self.clocks["terminal_scoring_cpu_ns"] = process_time_ns() - start
            return result

        start = now()
        with (patch.object(self.kernel, "ecef_states", self.states_at),
              patch.object(self.kernel, "prepare_phase_geometry", self.phase),
              patch.object(short_circuit, "evaluate_terminal", record_terminal)):
            self.decision = self.proof(tracks, reader, region, terminal_only=True)
        self.clocks.update(elapsed(start))
        if len(self.states) != 2 or self.geometry is None:
            raise ValueError("Saved proof did not use both original geometry stages")
        return self

    def lattice_scores(self, tracks, catalogue, region):
        # Replay the already computed bank. The exhaustive score check is off-clock.
        projections = []

        def collect(*args, **options):
            values = self.projector(*args, **options)
            projections.append(values)
            return values

        cached = iter(self.states)

        def supplied(cat, _origin, knots):
            times, labels, values = next(cached)
            if not np.array_equal(times, knots) or labels != tuple(cat.satellite_numbers):
                raise ValueError("Exhaustive scorer no longer requests the same bank")
            return values

        with patch.object(self.kernel, "ecef_states", supplied):
            points, score, _ = self.kernel._prepare_probe_scores(tracks, catalogue.catalogue, region)
        for point in points:
            with patch.object(self.kernel, "phase_linear_frequency", collect):
                row = score(point)
            projection, = projections
            projections.clear()
            yield row, projection


def lattice_error(control, approximation):
    maxima = dict(frequency_hz=0., tangent_hz_per_s=0., score=0., horizon_signs=0, owner_votes=0)
    points = votes = cells = 0
    for (a, (f0, h0, t0)), (b, (f1, h1, t1)) in zip(control, approximation, strict=True):
        if (a["xy_km"] != b["xy_km"] or a["side"] != b["side"]
                or a["owners"].keys() != b["owners"].keys() or a["receiver_scores"].keys() != b["receiver_scores"].keys()
                or f0.shape != f1.shape):
            raise ValueError("The matched geographic point or track labels changed")
        maxima["horizon_signs"] += int(np.count_nonzero((h0 >= 0) != (h1 >= 0)))
        maxima["owner_votes"] += sum(a["owners"][key] != b["owners"][key] for key in a["owners"])
        maxima["frequency_hz"] = max(maxima["frequency_hz"], float(np.max(abs(f0 - f1))))
        maxima["tangent_hz_per_s"] = max(maxima["tangent_hz_per_s"], float(np.max(abs(t0 - t1))))
        score_deltas = [abs(a["score"] - b["score"])]
        score_deltas.extend(abs(a["receiver_scores"][key] - b["receiver_scores"][key]) for key in a["receiver_scores"])
        if not np.isfinite(score_deltas).all():
            raise ValueError("Nonfinite regional scores")
        maxima["score"] = max(maxima["score"], *score_deltas)
        points += 1
        votes += len(a["owners"])
        cells += f0.size
    return dict(maxima, points=points, track_votes=votes, orbit_time_cells=cells)


def run(output):
    machine = host()
    publication, specification = configuration()
    from leo.contracts.digests import canonical_digest
    from dense_geographic_projection import checked_runtime
    from full_short_run import geographic_projection
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard as guard

    native, archive, offer, binary, control, research, request = bound_input()
    kernel, _ = checked_runtime()
    installed = algo08_position.solve
    result = {}

    def observe(document, reader, assets, region):
        if (document is not native or reader.root != archive or region.document() != offer
                or file_hash(assets / "tracks.json") != INPUT_PINS["tracks"]):
            raise ValueError("Expected the original signed saved input and installed graph")
        with handoff(reader) as (live, handoff_counts, _), geographic_projection(binary) as projection_counts:
            def inspect(prepared, offered, _bound, _stages, **_options):
                tracks = prepared["tracks"]
                catalogue = live.match(tracks, reader)
                if (catalogue is None or tuple(offered.center) != tuple(region.center)
                        or offered.width_km != region.width_km):
                    raise ValueError("Prepared causal proof did not match original input")
                exact = ProofPass(kernel, guard.causal_probes, kernel.phase_linear_frequency).evaluate(tracks, reader, offered)
                baseline = research["early_regional"][0]["result"]
                if canonical_digest(baseline) != canonical_digest(exact.decision):
                    raise ValueError("Exact proof must reproduce the archived physical candidate")
                candidate = ProofPass(kernel, guard.causal_probes, kernel.phase_linear_frequency,
                                      mode="candidate").evaluate(tracks, reader, offered)
                delta = dict(control=exact.clocks, candidate=candidate.clocks,
                             savings_cpu_s=exact.clocks["cpu_s"] - candidate.clocks["cpu_s"],
                             savings_elapsed_s=exact.clocks["elapsed_s"] - candidate.clocks["elapsed_s"])
                charged_projections = dict(projection_counts)
                raw = candidate.fine.raw_approximation
                approximate = candidate
                if raw is not None and candidate.fine.audit["fallback"]:
                    times, labels, _ = candidate.states[1]
                    approximate = ProofPass(kernel, guard.causal_probes, kernel.phase_linear_frequency,
                                            replay=(candidate.states[0], (times, labels, raw)))
                    approximate.evaluate(tracks, reader, offered)

                verification = dict(exact_screen=all(np.array_equal(x, y, equal_nan=True)
                                                     for x, y in zip(exact.states[0][2], candidate.states[0][2], strict=True)),
                                    fine_catalogue=exact.states[1][1] == candidate.states[1][1],
                                    returned_decision=canonical_digest(exact.decision) == canonical_digest(candidate.decision),
                                    returned_visits=exact.visited == candidate.visited)
                error = None
                if raw is not None and exact.states[1][1] == approximate.states[1][1]:
                    states = state_error(exact.states[1][2], raw)
                    drift = lattice_error(exact.lattice_scores(tracks, catalogue, offered),
                                          approximate.lattice_scores(tracks, catalogue, offered))
                    maxima = dict(states, **drift)
                    error = dict(maxima, raw_approximation_decision=approximate.decision,
                                 raw_approximation_visits=approximate.visited,
                                 accepted_science=(all(maxima[key] <= value for key, value in LIMITS.items())
                                                   and not any(maxima[key] for key in ("horizon_signs", "owner_votes", "usable_changes"))
                                                   and canonical_digest(exact.decision) == canonical_digest(approximate.decision)
                                                   and exact.visited == approximate.visited))
                result.update(clocks=delta, verification=verification, policy=candidate.fine.audit,
                              original_proof=exact.decision, returned_proof=candidate.decision,
                              visited_control=exact.visited, visited_returned=candidate.visited,
                              comparison=error, charged_projection=charged_projections)
                return dict(status="withheld", reason=STOP, arms={arm: dict(latlon=None) for arm in ARMS})

            with patch.object(v5_core, "infer", inspect):
                reply = installed(document, reader, assets, region)
            result["catalogue_handoff"] = dict(handoff_counts)
        return reply

    with patch.object(algo08_position, "solve", observe):
        study = solve(publication, specification, native, archive, offer)
    if (study["reason"] != STOP or result["catalogue_handoff"].get("prepared_catalogues") != 1
            or not result["verification"]["exact_screen"] or not result["verification"]["fine_catalogue"]):
        raise ValueError("The saved replay failed original preparation or proof scope")
    write(output, dict(result, case="DS30-0016", native_sha256=control["native_sha256"], request=request,
                       source_sha256=file_hash(Path(__file__)), machine=machine, limits=LIMITS, cadence_s=STEP,
                       saved_graph_preparation_and_proof_cpu_s=study["cpu_s"], exit_reason=study["reason"]))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
