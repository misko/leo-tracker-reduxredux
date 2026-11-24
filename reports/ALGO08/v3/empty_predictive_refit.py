"""Compare already paid curved history against the installed empty linear refit."""

from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

from nomination_handoff import same


SOURCE_PINS = {
    "history_policy": "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1",
    "history_position": "00e349de1a25ac62fb287f970a005737675b5f2e6d45273baa9c914e8a7918f0",
    "predictive_linear": "1c1930b8fc71b6fafd43fa744661a785b7d243b74b1ab39ab1f59d8fe800dcc6",
}
PHASE = "        reference = np.clip(phase, -15, 15)\n"
FINAL = "    c = p.calculate(anchor)\n"


def instrument(stock):
    source = getsource(stock)
    signature = "*, rounds=5, iterations=48):"
    if any(source.count(mark) != 1 for mark in (PHASE, FINAL, signature)):
        raise ValueError("Unsupported original curved refit checkpoints")
    source = (source.replace(signature, "*, rounds=5, iterations=48, observe):")
              .replace(PHASE, "        following = np.clip(phase, -15, 15)\n"
                       "        observe.phase(reference, following)\n        reference = following\n")
              .replace(FINAL, FINAL + "    observe.last(p, c)\n"))
    namespace = dict(stock.__globals__)
    exec(compile(source, stock.__code__.co_filename, "exec"), namespace)
    return namespace[stock.__name__]


class CurvedCapture:
    def __init__(self, scan, inputs):
        self.scan = scan
        self.inputs = deepcopy(inputs)
        self.phase_changes = []
        self.linear_options = False
        self.phase_reference = None
        self.replay_difference = None
        self.record = None
        self.bookkeeping_ns = 0

    def phase(self, before, after):
        start = process_time_ns()
        self.phase_changes.append(float(max(abs(after - before))))
        self.bookkeeping_ns += process_time_ns() - start

    def last(self, problem, result):
        start = process_time_ns()
        self.linear_options = bool(getattr(problem, "linear_slices", []))
        self.phase_reference = problem.reference.copy()
        coefficient = result["coefficient"]
        self.replay_difference = float(max(abs(coefficient - coefficient)))
        self.bookkeeping_ns += process_time_ns() - start

    def readout(self, scan, inputs, entries):
        from math import isfinite

        if (entries or scan is not self.scan or not same(self.inputs, inputs)
                or self.record is None or self.linear_options or self.phase_reference is None
                or not self.phase_changes or not isfinite(self.replay_difference)
                or not all(map(isfinite, self.phase_changes))):
            return None
        curved = self.record
        history = [dict(fit=deepcopy(row["fit"]), phase_change_s=change)
                   for row, change in zip(curved["history"], self.phase_changes, strict=True)]
        return dict(
            endpoint_east_north_km=curved["endpoint_east_north_km"].copy(),
            endpoint_latlon=deepcopy(curved["endpoint_latlon"]),
            history=history,
            phase_reference=self.phase_reference.copy(),
            state=deepcopy(curved["state"]),
            gates=deepcopy(curved["gates"]),
            linear_gates=[],
            active_points=curved["active_points"],
            additional_predictive_points=0,
            RMS_hz=curved["RMS_hz"],
            negative_twice_elbo=curved["negative_twice_elbo"],
            curved_negative_twice_elbo=curved["negative_twice_elbo"],
            linear_predictive_objective=0.0,
            calibration_replay_max_coefficient_difference=self.replay_difference,
            final_phase_change_s=self.phase_changes[-1],
        )


def compatible(policy, curved, linear, map_arms):
    return (map_arms is None and policy.refit is curved.refit and policy.linear_refit is linear.refit
            and curved.make_problem is linear.make_problem and curved.fit is linear.fit
            and curved.retained_metrics is linear.retained_metrics)


def independently_passes(policy, record, half_width):
    # The installed predicate tests both arms with the same thresholds and no cross-arm inputs.
    return policy.pair_passes(dict.fromkeys(policy.ARMS, record), include_linear=True,
                              half_width_km=half_width)


@contextmanager
def measured_history(audit):
    from leo.analysis.localization_v3 import history_policy as policy, history_position as curved, predictive_linear as linear

    setup = process_time_ns()
    sources = {module.__name__.rsplit(".", 1)[-1]: sha256(Path(module.__file__).read_bytes()).hexdigest()
               for module in (policy, curved, linear)}
    if sources != SOURCE_PINS:
        raise ValueError("The original named history sources changed")
    original = policy.history_policy
    audit["sources"] = sources
    audit["setup_cpu_ns"] = process_time_ns() - setup

    def capture_policy(*args, **kwargs):
        policy_started = process_time_ns()
        scan = args[0]
        setup = process_time_ns()
        match = compatible(policy, curved, linear, kwargs.get("map_arms"))
        trace = dict(compatible=match, curved={}, linear={})
        audit["calls"].append(trace)
        if not match:
            return original(*args, **kwargs)
        fitted = instrument(curved.refit)
        ordinary_linear = policy.linear_refit
        captures = {}
        trace["setup_cpu_ns"] = process_time_ns() - setup

        def counted(name):
            ordinary = getattr(policy, name)

            def call(*args, **kwargs):
                start = process_time_ns()
                result = ordinary(*args, **kwargs)
                trace[name + "_cpu_ns"] = process_time_ns() - start
                return result

            return call

        def capture(scan, node, keep, arm, weights, means, multiplier, nu):
            started = process_time_ns()
            capture = CurvedCapture(scan, (node, keep, weights, means, multiplier, nu))
            captures[arm] = capture
            initial_ns = process_time_ns() - started
            begin = process_time_ns()
            record = fitted(scan, node, keep, arm, weights, means, multiplier, nu, observe=capture)
            capture.record = record
            sample = dict(total_cpu_ns=process_time_ns() - begin, capture_cpu_ns=initial_ns + capture.bookkeeping_ns,
                          points=record["active_points"], clipped_change_s=capture.phase_changes,
                          unclipped_change_s=[entry["phase_change_s"] for entry in record["history"]])
            trace["curved"].setdefault(arm, []).append(sample)
            return record

        def compare(scan, node, keep, weights, means, model, arm, entries):
            start = process_time_ns()
            selected = captures.get(arm)
            preview = selected.readout(scan, (node, keep, weights, means, model["multiplier"], model["nu"]), entries) if selected else None
            preview_ns = process_time_ns() - start
            start = process_time_ns()
            stock = ordinary_linear(scan, node, keep, weights, means, model, arm, entries)
            sample = dict(stock_cpu_ns=process_time_ns() - start, candidate_cpu_ns=preview_ns,
                          offered_tracks=len(entries), active_points=stock["active_points"],
                          compatible_tracks=sum(row["compatible"] for row in stock["gates"]["tracks"]),
                          active_tracks=len(stock["gates"]["tracks"]),
                          compatible_linear_tracks=sum(row["compatible"] for row in stock["linear_gates"]),
                          endpoint=stock["endpoint_east_north_km"], rf_rms_hz=stock["RMS_hz"],
                          phase_change_s=stock["final_phase_change_s"],
                          independent_pass=independently_passes(policy, stock, scan.search_region.half_width_km),
                          candidate_exact=None if preview is None else same(preview, stock))
            trace["linear"][arm] = sample
            if sample["candidate_exact"] is False:
                sample["different_fields"] = [key for key in stock if not same(preview[key], stock[key])]
            return stock

        with (patch.object(policy, "refit", capture), patch.object(policy, "linear_refit", compare),
              patch.object(policy, "confidence_for", counted("confidence_for")),
              patch.object(policy, "select_entries", counted("select_entries"))):
            result = original(*args, **kwargs)
        trace.update({key: result.get(key) for key in ("status", "fallback", "linear_paired_valid",
                                                       "linear_offered_tracks", "linear_offered_points",
                                                       "linear_used_points", "curved_gate_history")})
        trace["half_width_km"] = scan.search_region.half_width_km
        trace["total_cpu_ns"] = process_time_ns() - policy_started
        raise HistoryComplete(result)

    with patch.object(policy, "history_policy", capture_policy):
        yield


class HistoryComplete(BaseException):
    """Exit immediately after the original decision and before signed fitting."""

    def __init__(self, result):
        self.result = result
