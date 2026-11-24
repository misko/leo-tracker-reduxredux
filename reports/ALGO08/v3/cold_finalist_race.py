"""Pause and selectively complete the original full-objective cold finalists."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


OPTIMIZER_SHA = "5bceea78eaece66c20f1e12c1fd109182a8cc5cc2e8b6d410f2d68d93e9110a3"
ENDPOINT_SHA = "b6cdb1a7a2da927583caca002610b5e18a3725dceb21177705ab719ab24dece5"
ITERATIONS = 48
PREFIX_ITERATIONS = 2
EXPECTED_ERRORS = (ValueError, ArithmeticError, np.linalg.LinAlgError)


def stock_coroutine(operation):
    """Insert a yield into the pinned optimizer while preserving all its state."""
    from tools.pipeline_eval.variants import compact_cavity_optimizer

    source_path = Path(compact_cavity_optimizer.__file__)
    if (operation is not compact_cavity_optimizer.bounded_secant
            or sha256(source_path.read_bytes()).hexdigest() != OPTIMIZER_SHA):
        raise ValueError("The active installed nonlinear optimizer differs from the pinned secant solver")
    source = getsource(operation)
    loop = '    for _ in range(iterations):\n'
    end = '            jacobian = None\n    return dict('
    if source.count(loop) != 1 or source.count(end) != 1:
        raise ValueError("The pinned secant optimizer's pause point changed")
    checkpoint = """            jacobian = None
        yield dict(parameters=x.copy(), score=score, drop=score_before_iteration - score, evaluations=evaluations)
    return dict("""
    source = source.replace(loop, loop + "        score_before_iteration = score\n").replace(end, checkpoint)
    namespace = dict(vars(compact_cavity_optimizer))
    exec(compile(source, str(source_path), "exec"), namespace)
    return namespace[operation.__name__]


def secant_port(operation):
    """Resolve the installed optimizer through the pinned endpoint reuse wrapper."""
    from tools.pipeline_eval.variants import algo08_endpoint_readout, compact_cavity_optimizer

    if operation is compact_cavity_optimizer.bounded_secant:
        return operation, None
    if (operation.__globals__ is vars(algo08_endpoint_readout)
            and operation.__qualname__ == "measured_readout.<locals>.solve"
            and sha256(Path(algo08_endpoint_readout.__file__).read_bytes()).hexdigest() == ENDPOINT_SHA):
        cells = dict(zip(operation.__code__.co_freevars, operation.__closure__, strict=True))
        return cells["original"].cell_contents, cells["original"]
    raise ValueError("Unexpected optimizer binding in the cold finalist route")


@contextmanager
def resume_port(position, cell, pause):
    def resume(*_args, **_kwargs):
        return pause.finish()

    if cell is None:
        with patch.object(position, "bounded_gauss_newton", resume):
            yield
    else:
        original = cell.cell_contents
        cell.cell_contents = resume
        try:
            yield
        finally:
            cell.cell_contents = original


class Pause:
    def __init__(self, optimizer, residual, lower, upper):
        self.stream = optimizer(residual, np.zeros(2), lower, upper, iterations=ITERATIONS)
        self.done = None

    def advance(self):
        if self.done is not None:
            return None
        try:
            return next(self.stream)
        except StopIteration as end:
            self.done = end.value
            return None

    def prefix(self):
        state = None
        for _ in range(PREFIX_ITERATIONS):
            state = self.advance()
            if state is None:
                state = dict(parameters=self.done["parameters"], score=self.done["score"],
                             drop=0., evaluations=self.done["evaluations"], stopped=self.done["stopped"])
                break
        return state

    def finish(self):
        while self.advance() is not None:
            pass
        return self.done

    def close(self):
        self.stream.close()


def choose(prefix, half_width):
    if len(prefix) != 3:
        return None, "not_three_finalists", []
    scores = np.array([part["score"] for part in prefix])
    points = np.array([part["parameters"] for part in prefix])
    recent = np.array([part["drop"] for part in prefix])
    if (points.shape != (3, 2) or not all(np.isfinite(a).all() for a in (scores, points, recent))
            or np.any(recent < 0.) or not np.isfinite(half_width) or half_width <= 0.5):
        return None, "invalid_prefix", []
    if np.any(np.abs(points) > half_width - 0.5):
        return None, "near_region_face", []
    leader = int(np.argmin(scores))
    comparisons = []
    for i in range(3):
        if i == leader:
            continue
        margin = float(max(.01, .01*abs(scores[leader]), 4*max(recent[leader], recent[i])))
        comparisons.append(dict(other=i+1, gap=float(scores[i]-scores[leader]), required=margin))
    if any(item["gap"] <= item["required"] for item in comparisons):
        return None, "ambiguous_gap", comparisons
    return leader, "winner_raced", comparisons


def audit_overlap(nodes):
    from leo.analysis.localization_v3.discovery import signature

    rows = [dict((piece[0], piece[2:]) for piece in signature(node)) for node in nodes]
    records = []
    for i, a in enumerate(rows):
        for j, b in enumerate(rows[i+1:], i+1):
            shared = a.keys() & b.keys()
            records.append(dict(ranks=[i+1, j+1], left=len(a), right=len(b), shared_tracks=len(shared),
                same_norad=sum(a[k][0] == b[k][0] for k in shared),
                same_alias=sum(a[k][1] == b[k][1] for k in shared),
                same_assignment=sum(a[k] == b[k] for k in shared)))
    return records


def readout(node, model, fit, posterior):
    score = float(fit["score"]) if np.isfinite(fit["score"]) else None
    return node, np.asarray(fit["parameters"]), dict(zip(model.labels, np.clip(posterior, -15., 15.), strict=True)), score


def fit_info(branch, model, fit, posterior, cpu, first):
    return dict(branch=branch+1, score=finite_score(fit),
                point=np.asarray(fit["parameters"]), labels=model.labels, posterior=posterior,
                first_score=finite_score(first), first_evaluations=first["evaluations"],
                second_evaluations=fit["evaluations"], stopped=fit["stopped"], cpu_ns=cpu)


def finite_score(fit):
    return float(fit["score"]) if np.isfinite(fit["score"]) else None


def record_invalid_prefix(prefix):
    def value(number):
        return float(number) if np.isfinite(number) else None

    for item in prefix:
        item.update(score=value(item["score"]), drop=value(item["drop"]),
                    parameters=[value(x) for x in item["parameters"]])


def original_fits(scan, nodes):
    from leo.analysis.localization_v3 import position

    outcomes, detail = {}, []
    for index, node in enumerate(nodes):
        start = process_time_ns()
        model, fit, history = position.refreshed(scan, scan.radio_sigma_hz, node, "c0", rounds=2,
                                                iterations=ITERATIONS)
        cpu = process_time_ns()-start
        phases = history[-1]["posterior_phase_s"]
        outcomes[index] = readout(node, model, fit, phases)
        detail.append(fit_info(index, model, fit, phases, cpu, history[0]["fit"]))
    return outcomes, detail


def partial_fits(scan, nodes, half_width, details):
    from leo.analysis.localization_v3 import position

    if len(nodes) != 3:
        details["routing"] = "not_three_finalists"
        return original_fits(scan, nodes)
    contenders = []
    try:
        active, endpoint_cell = secant_port(position.bounded_gauss_newton)
        optimizer = stock_coroutine(active)
        for branch, node in enumerate(nodes):
            start = process_time_ns()
            model = position.NormalPosition(scan, node, scan.radio_sigma_hz, False,
                                            reference=np.zeros(len({r["candidate_index"] for r in node["seed"]["rows"]})))
            pause = Pause(optimizer, model.residual, model.lower, model.upper)
            contenders.append((model, pause))
            state = pause.prefix()
            details["prefix"].append(dict(branch=branch+1, cpu_ns=process_time_ns()-start, **state))
        leader, reason, gaps = choose(details["prefix"], half_width)
        details.update(routing=reason, gaps=gaps)
        if reason == "invalid_prefix":
            record_invalid_prefix(details["prefix"])
        outcomes, completed = {}, []
        for index in (range(3) if leader is None else (leader,)):
            start = process_time_ns()
            base, pause = contenders[index]
            # Keep the released endpoint readout around the resumed solver.
            with resume_port(position, endpoint_cell, pause):
                first = position.fit(base, iterations=ITERATIONS)
            anchor = np.array(first["parameters"])
            reference = np.clip(base.state(anchor)["phases"][base.labels], -15., 15.)
            model = position.NormalPosition(scan, nodes[index], scan.radio_sigma_hz, False, reference=reference)
            fit = position.fit(model, anchor, iterations=ITERATIONS)
            phases = model.state(np.array(fit["parameters"]))["phases"][model.labels]
            outcomes[index] = readout(nodes[index], model, fit, phases)
            completed.append(fit_info(index, model, fit, phases, process_time_ns()-start, first))
            if outcomes[index][-1] is None:
                raise ValueError("Non-finite resumed finalist")
        return outcomes, completed
    except EXPECTED_ERRORS as exc:
        details.update(routing="full_restart_on_invalid", invalid=f"{type(exc).__name__}: {exc}")
        record_invalid_prefix(details["prefix"])
        return original_fits(scan, nodes)
    finally:
        for _, pause in contenders:
            pause.close()


def refine(mode, prepared, region, bound, *, checkpoint=None):
    from blind_joint_finish import digest
    from tools.pipeline_eval.variants import v5_core

    scan = v5_core.scan_context(prepared, region, digest(prepared["noise"]), bound, "previous")
    candidates = v5_core.ranked_initial_nodes(scan)[:3]
    details = dict(overlap=audit_overlap(candidates), prefix=[], routing="all_finalists")
    if mode == "control":
        outcomes, completed = original_fits(scan, candidates)
    else:
        outcomes, completed = partial_fits(scan, candidates, region.half_width_km, details)
    if checkpoint is not None:
        checkpoint(scan, candidates, outcomes)
    valid = [i for i, row in outcomes.items() if row[-1] is not None]
    if not valid:
        raise ValueError("No finite cold ranked assignment")
    selected = min(valid, key=lambda i: (outcomes[i][-1], i))
    node, point, reference, _ = outcomes[selected]
    scores = [outcomes[i][-1] if i in outcomes else None for i in range(len(candidates))]
    details.update(completed=completed, scores=scores, branch=selected+1, east_north_km=point,
                   latlon=region.latlon(point), catalogue=len(scan.norads))
    return node, point, reference, details
