"""Compare a prespecified covariance null against the frozen packed receiver."""

import argparse
import ctypes as ct
import gzip
import json
import sys
from collections import Counter, defaultdict
from contextlib import ExitStack
from math import ceil
from pathlib import Path

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Receiver, digest, read_archive, read_simulated_prefix
from .receiver_covariance_overlay import build_probe

FROZEN_SHA = "950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13"
PROSPECTIVE = {"DS29-0082", "DS29-0174", "DS29-0519"}
ARMS = ("frozen", "control", "primary", "residual")
SEED = 30261991
NULL_DRAWS = 256


class Covariance(ct.Structure):
    _fields_ = [
        ("trace", ct.c_double), ("largest", ct.c_double), ("leading_pair", ct.c_double),
        ("prefix_ns", ct.c_uint64), ("covariance_ns", ct.c_uint64), ("skipped", ct.c_int),
    ]


class ProbeReceiver(Receiver):
    def __init__(self, binary, asset):
        super().__init__(binary, asset)
        self.reset = self.lib.experimental_receiver_covariance_reset
        self.reset.argtypes = [ct.c_uint, ct.c_double, ct.c_double]
        self.reset.restype = None
        self.read = self.lib.experimental_receiver_covariance_read
        self.read.argtypes = [ct.POINTER(Covariance), ct.c_uint]
        self.read.restype = ct.c_uint

    def observe(self, samples, lane, center, gate=0, limits=(0., 0.)):
        self.reset(gate, *limits)
        factors, cpu, wall = self.timed(samples, lane, center)
        rows = (Covariance * 2)()
        passes = self.read(rows, len(rows))
        if not 1 <= passes <= 2:
            raise ValueError("Missing primary or excess residual covariance")
        if len(factors) and passes != 2:
            raise ValueError("Frozen receiver verifies factors after both covariance passes")
        records = [{key: getattr(row, key) for key, _ in Covariance._fields_}
                   for row in rows[:passes]]
        return factors, cpu, wall, records


def pilot_assets(assets):
    for edge in ("lower", "upper"):
        pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
        if pilot.shape != (133413,):
            raise ValueError("Unexpected pilot asset")
        yield edge, pilot


def calibrate(receivers):
    rng = np.random.default_rng(SEED)
    data = np.zeros((200000, 2, 2), dtype="<i2")
    controls = {}
    for edge, receiver in receivers.items():
        noise = []
        for _ in range(NULL_DRAWS):
            data[:, 0, :] = np.rint(rng.standard_normal((200000, 2)) * 256)
            factors, _, _, passes = receiver.observe(data, 0, 0., gate=4)
            if factors or len(passes) != 1 or not passes[0]["skipped"]:
                raise ValueError("Noise calibration must stop immediately after covariance")
            noise.append((passes[0]["largest"], passes[0]["leading_pair"]))
        quantile_index = ceil(.95 * NULL_DRAWS) - 1
        limits = tuple(np.sort(noise, axis=0)[quantile_index])
        controls[edge] = dict(limits=limits, raw_shares=noise)
    return controls


def load_panels(prospective, weak, simulation):
    groups = {
        "prospective": [(r, data) for r, data in read_archive(prospective, 80)
                        if r["case"] in PROSPECTIVE],
        "weak": list(read_archive(weak, 18)),
    }
    if len(groups["prospective"]) != 30 or len(groups["weak"]) != 18:
        raise ValueError("Expected all prespecified physical visits")
    if any(row["case"] in PROSPECTIVE for row, _ in groups["weak"]):
        raise ValueError("Physical control and challenge recordings overlap")
    for row, data in read_simulated_prefix(simulation, 40):
        groups.setdefault(row["case"], []).append((row, data))
    seen = set()
    for key, rows in groups.items():
        digests = {row["sha256"] for row, _ in rows}
        if len(digests) != len(rows) or seen.intersection(digests):
            raise ValueError(f"Evaluation waveforms overlap in {key}")
        seen.update(digests)
    return groups


def continuation(probe, history, factors):
    _, selected, votes = history.select(dict(
        probe, candidates=[Receiver.criteria(*row) for row in factors],
    ))
    return (None if selected is None else factors[selected], votes)


def compare(frozen, candidate):
    old, new = frozen["factors"], candidate["factors"]
    missed = Counter(row[0] for row in (Counter(old) - Counter(new)).elements())
    extra = Counter(row[0] for row in (Counter(new) - Counter(old)).elements())
    return dict(changed_lanes=old != new, lost_primary=missed[0], lost_residual=missed[1],
                added_primary=extra[0], added_residual=extra[1],
                selected=frozen["selected"] is not None,
                candidate_selected=candidate["selected"] is not None,
                selected_changed=frozen["selected"] != candidate["selected"],
                votes_changed=frozen["votes"] != candidate["votes"],
                skipped_passes=sum(row["skipped"] for row in candidate["passes"]))


def trial(rows, stock, receivers, calibration):
    runs = []
    evidence = []
    for repeat in range(2):
        metrics = {arm: Counter() for arm in ARMS}
        counts = {arm: Counter() for arm in ARMS[1:]}
        histories = defaultdict(Continuation)
        for index, (row, samples) in enumerate(rows):
            target, acq = row["target"], row["acquisition"]
            rf = acq["actual_if_center_hz"] + target["lnb_lo_hz"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                probe = dict(receiver_id=lane, channel=target["channel"], actual_rf_hz=rf,
                             valid_start_counter=acq["sample_start"])
                first = (index + lane + repeat) % len(ARMS)
                order = ARMS[first:] + ARMS[:first]
                if repeat:
                    order = order[::-1]
                results = {}
                for arm in order:
                    edge = row["edge"]
                    if arm == "frozen":
                        factors, cpu, wall = stock[edge].timed(samples, lane, center)
                        passes = []
                    else:
                        mode = ARMS.index(arm) - 1
                        limits = calibration[edge]["limits"]
                        factors, cpu, wall, passes = receivers[edge].observe(
                            samples, lane, center, mode, limits,
                        )
                    selected, votes = continuation(probe, histories[(arm, row["case"])], factors)
                    results[arm] = dict(
                        factors=factors, selected=selected, votes=votes, passes=passes,
                    )
                    metrics[arm].update(dict(cpu_ns=cpu, wall_ns=wall,
                                             primary=sum(f[0] == 0 for f in factors),
                                             residual=sum(f[0] == 1 for f in factors)))
                    for pass_id, observed in zip(("primary", "residual"), passes, strict=False):
                        metrics[arm].update({
                            f"{pass_id}_passes": 1,
                            f"{pass_id}_prefix_ns": observed["prefix_ns"],
                            f"{pass_id}_covariance_ns": observed["covariance_ns"],
                        })
                for arm in ARMS[1:]:
                    counts[arm].update(compare(results["frozen"], results[arm]))
                if not repeat:
                    evidence.append(dict(key=row["key"], lane=lane, edge=row["edge"], arms=results))
        control = counts["control"]
        if any(control[key] for key in ("changed_lanes", "selected_changed", "votes_changed")):
            raise ValueError("Instrumentation differs from the frozen receiver")
        runs.append(dict(metrics=metrics, counts=counts))
    if runs[0]["counts"] != runs[1]["counts"]:
        raise ValueError("Covariance and continuation results differ across repeats")
    inputs = dict(cases=sorted({row["case"] for row, _ in rows}),
                  windows=[(row["key"], row["sha256"]) for row, _ in rows])
    return dict(visits=len(rows), lanes=2 * len(rows), inputs=inputs, runs=runs, rows=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_ = commands.add_parser("build")
    compile_.add_argument("output", type=Path)
    run = commands.add_parser("compare")
    for argument in ("frozen", "probe", "assets", "prospective", "weak", "simulation"):
        run.add_argument(argument, type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build_probe(args.output)
        return
    if digest(args.frozen.read_bytes()) != FROZEN_SHA:
        raise ValueError("Expected the genuine packed receiver")
    with ExitStack() as stack:
        stock, receivers = {}, {}
        for edge, pilot in pilot_assets(args.assets):
            stock[edge] = Receiver(args.frozen, pilot)
            receivers[edge] = ProbeReceiver(args.probe, pilot)
            stack.callback(stock[edge].close)
            stack.callback(receivers[edge].close)
        calibration = calibrate(receivers)
        panels = load_panels(args.prospective, args.weak, args.simulation)
        groups = {key: trial(rows, stock, receivers, calibration) for key, rows in panels.items()}
    result = dict(frozen=FROZEN_SHA, instrumented=digest(args.probe.read_bytes()), seed=SEED,
                  null_draws_per_edge=NULL_DRAWS, calibration=calibration, groups=groups)
    sys.stdout.buffer.write(gzip.compress(json.dumps(result, allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    main()
