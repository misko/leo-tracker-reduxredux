"""Nominate inline same-window full checks and score sealed field packet opportunities."""

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import json
from math import isfinite
import os
from pathlib import Path
import sys

from .calibration_transport import FIELD, FIRST30, signed_attempt
from .ds30_paired_inputs import checked, digest


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"
sys.path.insert(0, str(HERE))  # The existing signed-packet and donor helpers use local research imports.
import signed_cfo_time_readout as signed
from matched_donor_0049 import same_carrier


DEVELOPMENT = ("DS30-0049",)
HELD = ("DS30-0086", "DS30-0144", "DS30-0170", "DS30-0262")
COHORTS = {"development": DEVELOPMENT, "held": HELD}
CLASSES = ("missing", "disagreeing")
STREAM = ("edge", "channel", "actual_rf_hz", "receiver_id")
HERTZ = "fractional_tracking_cfo_hz"
BUDGET_INTERVAL = 16
SAMPLE_RATE = 10_000_000
JOINT = {
    "DS30-0049": "ds30-0049-joint-recovery.json.gz",
    "DS30-0086": "ds30-0086-joint-recovery.json.gz",
}


def saved_only(event, params, *, prediction=False):
    if event == "open" and isinstance(params[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(params[0])))
        if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
                or path.name.endswith((".ci16.zst", ".tle", ".tle.gz")) or "tle" in path.parts or
                (prediction and ("installed" in path.parts or "exact-named-raw-witness.json" == path.name
                                 or "reference-audit.json" == path.name))):
            raise ValueError(f"The saved evidence boundary excludes {path}")


def forecast(history, now):
    previous = [(counter, hz) for counter, hz in history if hz is not None and 0 < now-counter <= 8*SAMPLE_RATE]
    if len(previous) < 3:
        return None
    (a, x), (b, y), (c, z) = previous[-3:]
    duration = (c-a)/SAMPLE_RATE
    age = (now-c)/SAMPLE_RATE
    if age > 2 or duration < .4:
        return None
    slope = (z-x)/duration
    error = abs(y - (x+slope*(b-a)/SAMPLE_RATE))
    if abs(slope) > 8_000 or error > 250:
        return None
    return z+slope*age, error


@dataclass
class StreamBudget:
    history: deque = field(default_factory=lambda: deque(maxlen=12))
    short_count: int = 0
    pending: dict | None = None

    def consider(self, observation, peer_positive):
        now = observation["counter"]
        factor = observation["factor"]
        hz = factor[HERTZ] if factor is not None else None
        if (hz is not None and not isfinite(hz)) or (self.history and now <= self.history[-1][0]):
            raise ValueError("Expected finite signed CFO and increasing hardware chronology")
        opened = None
        if observation["short"]:
            self.short_count += 1
            phase = self.short_count % BUDGET_INTERVAL
            if self.short_count >= BUDGET_INTERVAL and phase == 0:
                opened = self.pending = dict(lanes=[], chosen=None, reason=None)
            if self.pending:
                self.pending["lanes"].append(observation["id"])
                if self.pending["chosen"] is None:
                    predicted = forecast(self.history, now)
                    active_peer = bool(peer_positive and self.history and self.history[-1][1] is not None
                                       and now-self.history[-1][0] <= 2*SAMPLE_RATE)
                    reason = None
                    if hz is None and (predicted or active_peer):
                        reason = "expected_missing"
                    elif hz is not None and predicted and abs(hz-predicted[0]) > 250+2*predicted[1]:
                        reason = "forecast_departure"
                    elif phase == BUDGET_INTERVAL-1:
                        reason = "deadline"
                    if reason:
                        self.pending.update(chosen=observation["id"], reason=reason)
        self.history.append((now, hz))
        return opened


def schedule(opportunities):
    streams = defaultdict(StreamBudget)
    credits = []
    rows = iter(opportunities.values())
    for left, right in zip(rows, rows, strict=True):
        for row, peer in ((left, right), (right, left)):
            factor_count = len(row["row"]["candidates"])
            if factor_count != int(row["factor"] is not None):
                raise ValueError("The input is not the original unfiltered single-factor packet")
            stream = tuple(row["row"][name] for name in STREAM)
            opened = streams[stream].consider(row, peer["factor"] is not None)
            if opened is not None:
                credits.append(opened)
    return credits


def enrollment(snapshot, cohort):
    raw = checked(snapshot / "rows-with-relocations.jsonl", FIRST30)
    cases = COHORTS[cohort]
    rows = [x for line in raw.splitlines() if (x := json.loads(line))["verified_pair"] is True and x["case"] in cases]
    result = {(r["case"], r["algorithm"]): r for r in rows}
    if len(rows) != 2*len(cases) or set(result) != {(case, method) for case in cases for method in ("installed", "successor")}:
        raise ValueError("The recorded pairs do not fill the frozen small cohort")
    return result


def candidate_packet(row):
    result = signed_attempt(FIELD, row)
    pub = (FIELD / row["attempt"]).parent / "publication"
    raw = signed.document(pub / "unified-short-bootstrap.json")
    native = signed.read_native(pub, result["native_sha256"])
    source = native["source"]
    held = raw["held_anchor_route"]
    audit = raw["receiver_audit"]["native"]
    recipe = held["receiver_recipe"]
    base_recipe = {key: val for key, val in recipe.items() if key != "held_native_8ms"}
    base_detector = signed.canonical(base_recipe)
    original_analysis = signed.canonical(["cancellation", source["raw_recording_authority_digest"],
                                          base_detector[7:], source["probes"]])
    base = dict(native, source=dict(source, analysis_manifest_sha256=original_analysis), provenance=dict(
        native["provenance"], detector_sha256=base_detector, run_id="blind-compact-"+original_analysis[7:39]))
    opp = signed.opportunities(native)
    counts = dict(Counter("short_primary" if lane["short"] else "full" for lane in opp.values()))
    if (held["choice"]["route"] != "unfiltered" or held["refinement_calls"] or raw["native_sha256"] != result["native_sha256"]
            or held["native_sha256"] != result["native_sha256"] or recipe["aperture_samples"] != [200_000, 80_000]
            or recipe["rule"] != ["full"]+["short_primary"]*7 or recipe["streams"] != list(STREAM[:3])
            or recipe["installed_sha256"] != signed.FULL or recipe["shortened_sha256"] != signed.SPARSE
            or signed.canonical(recipe) != native["provenance"]["detector_sha256"]
            or held["parent_detector_sha256"] != base_detector or held["parent_native_sha256"] != signed.canonical(base)
            or held["selected"] != held["observed"] or held["selected"] != sum(len(x["candidates"]) for x in source["probes"])
            or counts != audit["native_calls"] or source["raw_recording_authority_digest"] != row["raw_authority_sha256"]):
        raise ValueError("The candidate packet does not reproduce the verified unfiltered receiver chronology")
    clock = {k: audit[k] for k in ("native_calls", "native_wall_ns", "native_cpu_ns")}
    return result, native, opp, clock


def predict(snapshot, cohort):
    roles = enrollment(snapshot, cohort)
    result = {}
    for case in COHORTS[cohort]:
        row = roles[case, "successor"]
        candidate, _, opportunities, clock = candidate_packet(row)
        try:
            plan = schedule(opportunities)
        except ValueError as error:
            raise ValueError(f"Invalid candidate schedule on {case}") from error
        result[case] = dict(candidate_result_sha256=row["attempt_result_sha256"],
                            candidate_native_sha256=candidate["native_sha256"], clock=clock, credits=plan)
    return dict(cohort=cohort, protocol_sha256=digest((HERE / "capped-revisit-protocol.md").read_bytes()),
                ledger_sha256=FIRST30, cases=result)


def target_sets(full, mixed):
    targets = {c: set() for c in CLASSES}
    for oid, lane in mixed.items():
        before, now = full[oid]["factor"], lane["factor"]
        if lane["short"] and before is not None:
            if now is None:
                targets["missing"].add(oid)
            elif not same_carrier(before, now):
                targets["disagreeing"].add(oid)
    targets["combined"] = set.union(*targets.values())
    return targets


def counts(selected, targets):
    return {name: dict(eligible=len(target), hits=len(target & selected),
                       recall=len(target & selected)/len(target) if target else None,
                       precision=len(target & selected)/len(selected) if selected else None)
            for name, target in targets.items()}


def owner_bounds(total_owned, total_positive, subset):
    if not 0 <= total_owned <= total_positive or not 0 <= subset <= total_positive:
        raise ValueError("Archived positive and owner totals contradict each other")
    return [max(0, total_owned-(total_positive-subset)), min(subset, total_owned)]


def compare(credits, targets):
    redeemed = [period for period in credits if period["chosen"] is not None]
    selected = {r["chosen"] for r in redeemed}
    periodic = {r["lanes"][0] for r in redeemed}
    independent = {r["lanes"][0] for r in credits}
    if len(selected) != len(periodic) or len(periodic) != len(redeemed):
        raise ValueError("Equal-spend schedules have inconsistent callback counts")
    uniform = {name: sum(len(target.intersection(period["lanes"]))/len(period["lanes"]) for period in redeemed)
               for name, target in targets.items()}
    groups = {name: {r["chosen"] for r in redeemed if r["reason"] == name}
              for name in ("expected_missing", "forecast_departure", "deadline")}
    result = dict(n=len(selected), independent_periodic_n=len(independent), nomination=counts(selected, targets),
                  periodic_same_spend=counts(periodic, targets), periodic_fixed=counts(independent, targets),
                  uniform_expected_hits=uniform,
                  by_reason={reason: dict(n=len(ids), targets=counts(ids, targets)) for reason, ids in groups.items()})
    return result, selected, periodic


def owners_readout(rows, targets, selected, periodic, full):
    from satellite_set_transfer import named_rows

    row, original = rows
    sets = named_rows(row["case"], original)
    positive = {oid for oid, lane in full.items() if lane["factor"] is not None}
    if sets:
        pinned = signed.owners(sets, original["evidence"]["owners"])
        if any(not values.keys() <= positive for values in pinned.values()):
            raise ValueError("The installed selected owner lacks a positive")
        return {arm: dict(exact=True, initial_owned=len(values), nomination=counts(selected, {
                    k: ids.intersection(values) for k, ids in targets.items()}), periodic=counts(periodic, {
                    k: ids.intersection(values) for k, ids in targets.items()})) for arm, values in pinned.items()}
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    pub = (FIELD / row["attempt"]).parent / "publication"
    detail = FastStandardAnalysisStore(pub).detail(original["evidence"]["receipt"]["run_id"])
    if detail["terminal_sha256"] != row["terminal_sha256"] or detail["input_sha256"] != original["native_sha256"]:
        raise ValueError("The archived total owner counts do not bind the field attempt")
    return {arm: dict(exact=False, initial_owned=side["associated_points"],
                      classes={k: {key: owner_bounds(side["associated_points"], len(positive), len(part))
                                   for key, part in (("eligible", ids), ("nomination", ids & selected),
                                                     ("periodic", ids & periodic))} for k, ids in targets.items()})
            for arm, side in detail["arms"].items()}


def score(snapshot, prediction, pin):
    frozen = signed.document(prediction, pin)
    cohort = frozen["cohort"]
    if predict(snapshot, cohort) != frozen:
        raise ValueError("The candidate-only decision receipt is not reproducible")
    rows = enrollment(snapshot, cohort)
    outcomes = {}
    for case in COHORTS[cohort]:
        row = rows[case, "installed"]
        original = signed_attempt(FIELD, row)
        selected_case, mixed_native, mixed, clock = candidate_packet(rows[case, "successor"])
        full = signed.read_native((FIELD / row["attempt"]).parent / "publication", original["native_sha256"])
        if original["raw_identity"] != selected_case["raw_identity"] or full["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
            raise ValueError("The two native packets do not share the original signed field case")
        full_lanes = signed.opportunities(full)
        signed.bind_pair(full, mixed_native, full_lanes, mixed)
        reference = target_sets(full_lanes, mixed)
        plan = frozen["cases"][case]["credits"]
        table, names, periodic = compare(plan, reference)
        owner_table = owners_readout((row, original), reference, names, periodic, full_lanes)
        means = {key: clock["native_"+key+"_ns"]["full"]/clock["native_calls"]["full"]/1.e9 for key in ("cpu", "wall")}
        deficit = rows[case, "successor"]["elapsed_s"]-row["elapsed_s"]/2
        outcomes[case] = dict(schedule=table, owner_coverage=owner_table, short_lanes=clock["native_calls"]["short_primary"],
                              v3_native_sha256=original["native_sha256"],
                              estimated_extra_s={metric: table["n"]*v for metric, v in means.items()},
                              original_elapsed_s={role: rows[case, role]["elapsed_s"] for role in ("installed", "successor")},
                              half_time_wall_deficit_s=deficit, after_projected_wall_deficit_s=deficit+table["n"]*means["wall"])
    aggregated = {name: {method: sum(o["schedule"][method][name]["hits"] for o in outcomes.values())
                         for method in ("nomination", "periodic_same_spend")} for name in (*CLASSES, "combined")}
    better = sum(o["schedule"]["nomination"]["combined"]["hits"] > o["schedule"]["periodic_same_spend"]["combined"]["hits"]
                 for o in outcomes.values())
    advance = better > len(outcomes)/2 and all(s["nomination"] > s["periodic_same_spend"] for s in aggregated.values())
    return dict(prediction_sha256=pin, cohort=cohort, cases=outcomes, aggregated_hits=aggregated,
                cases_with_more_combined_hits=better, advances=advance)


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("export", type=Path)
    commands = arguments.add_subparsers(dest="action", required=True)
    p = commands.add_parser("predict")
    p.add_argument("cohort", choices=COHORTS)
    s = commands.add_parser("score")
    s.add_argument("prediction", type=Path)
    s.add_argument("sha256")
    args = arguments.parse_args()
    sys.addaudithook(lambda event, params: saved_only(event, params, prediction=args.action == "predict"))
    result = predict(args.export, args.cohort) if args.action == "predict" else score(args.export, args.prediction, args.sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
