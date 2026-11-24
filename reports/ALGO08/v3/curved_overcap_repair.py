"""Audit an archived curved repair and authorize at most one extra original refit."""

from collections import defaultdict
from hashlib import sha256
import json
from math import floor, isfinite
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
CONTROL = Path("/tmp/leo-v3-field-stock-saved-0220-01")
SOURCE = Path("/tmp/leo-v3-integrated-original-batch/reports/ALGO08/v3")
INSTALLED = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3")
PINS = {
    CONTROL / "admission.json": "41f1d38215156a95deebf06bfe10237f477daa9c5b07d4eca8b09b3fdc4e137a",
    CONTROL / "process.json": "a51f6f216cb5b198d6f356104a6574da72844eba4ced4565ec445cb419e27e1f",
    CONTROL / "score.json": "329693cc9562cf7dc9e4828199003d4c332994ff9ee5a1f47b7d1e332c3e3eb3",
    CONTROL / "candidate/crossover-worker.json": "4d73fca4e001f27faf92106bb0180f7f7bfc31d093f6a11e734061de4b8bee2a",
    CONTROL / "candidate/exact-named-raw-witness.json": "982156b3591877e1f875d11dd7fc9e13618cb6fc5db013d37051a955ec83ff4b",
    SOURCE / "blind_joint_repair.py": "f89e80dd65606b065e4c8097d0d3204362993e070dc7dd3f2c2590dc2c32b2a0",
    SOURCE / "blind_joint_finish.py": "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",
    INSTALLED / "marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    INSTALLED / "conservative_recovery.py": "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656",
    INSTALLED / "history_policy.py": "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1",
}
ARM_NAMES = ("c0", "fitted_c")
LANE = re.compile(r"SCAN-RX([12])-CH([1-8])-T[0-9]+-RF[0-9.]+")


def checked(path, pin):
    content = path.read_bytes()
    if sha256(content).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved evidence or source changed: {path}")
    return content


def owner_slot(component):
    match = LANE.fullmatch(component)
    if match is None:
        raise ValueError("Unrecognized assigned Graph component")
    return tuple(map(int, match.groups()))


def groups(assignment, members):
    result = defaultdict(set)
    for track in members:
        result[assignment[track][0]].add(owner_slot(track))
    return result


def reconstruct(risk, half_width):
    attempt, = risk["lean_attempts"]
    repair, before = attempt["repair"], attempt["support"]
    if (repair["reason"] != "repair_rejection_cap" or attempt["reason"] != repair["reason"]
            or attempt["pair_passes"] or repair["attempted_refits"]):
        raise ValueError("The authentic comparison did not stop at the count screen")
    rank = attempt["cold"]["branch"]
    finalists = risk["two_centre_rank"]["finalist_signatures"]
    signature = finalists[rank-1]
    assignment = {key: (index, norad, alias) for key, index, norad, alias in signature}
    if len(assignment) != len(signature) or sorted({v[0] for v in assignment.values()}) != next(
        row["labels"] for row in attempt["cold"]["completed"] if row["branch"] == rank
    ):
        raise ValueError("The chosen saved rank and completed branch disagree")
    cold = set(before["cold_rejected_tracks"])
    salvage = {entry["component"]: entry["selected"] for entry in before["salvage"]}
    second = set(before["second_curved_rejections"])
    if set(salvage) != cold or not cold | second <= assignment.keys():
        raise ValueError("The archived repair masks are incomplete")
    recovered = {key for key, row in salvage.items() if row is not None}
    if sum(salvage[key]["points"] for key in recovered) != before["curved_restored"]:
        raise ValueError("The archived salvage did not preserve the original committed support")
    for key in recovered:
        row = salvage[key]
        assignment[key] = row["candidate_index"], row["norad"], row["alias"]
    active = (set(assignment)-cold | recovered)-second
    failures = {key for arm in ARM_NAMES for key in attempt["finish"][arm]["failed_curved"]}
    if failures != set(repair["removed_curved"]) or not failures <= active:
        raise ValueError("Paired gate failure union differs from the archived repair")
    kept = active-failures
    nominal, retained = groups(assignment, assignment), groups(assignment, kept)
    predicted = before["predictive_labels"]
    linear_failures = {key for arm in ARM_NAMES for key in attempt["finish"][arm]["failed_linear"]}
    surviving_norads = {assignment[key][1] for key in kept}
    surviving_bands = {(rx, ch > 4) for lanes in retained.values() for rx, ch in lanes}
    predicted_drops = sorted(key for key, norad, _ in predicted
                             if key in linear_failures or norad not in surviving_norads
                             or (owner_slot(key)[0], owner_slot(key)[1] > 4) not in surviving_bands)
    if (predicted_drops != repair["removed_predictive"] or repair["rejection_counts"]["predictive"][1] != 0
            or [len(active)+len(predicted), len(failures)+len(predicted_drops)] != repair["rejection_counts"]["tracks"]
            or before["rechecked_curved"] != repair["rejection_counts"]["curved"][0]
            or len(retained) != repair["curved_families"]):
        raise ValueError("Reconstructed nominal and retained support disagree with the repair receipt")
    physical = {key for key, lanes in nominal.items() if len(lanes) >= 2}
    singleton = sorted(key for key in physical if len(retained.get(key, ())) == 1)
    receivers = {rx for lanes in retained.values() for rx, _ in lanes}
    if len(receivers) != repair["receivers"]:
        raise ValueError("Intersection repair changed the receiver count")
    endpoints = {arm: attempt["finish"][arm]["east_north_km"] for arm in ARM_NAMES}
    passed = dict(receivers=len(receivers) == 2, families=len(retained) >= 2,
                  degrees=repair["residual_degrees_of_freedom"] > 0, orbital_modes=not singleton,
                  region=all(len(p) == 2 and all(isfinite(x) and abs(x) <= half_width+1e-8 for x in p)
                             for p in endpoints.values()))
    counts = repair["rejection_counts"]
    return dict(passed=passed, rank=rank, nominal_tracks=len(assignment), active_tracks=len(active), retained_tracks=len(kept),
                families=len(retained), physical_mode_families=len(physical), singleton_families=singleton,
                nominal_groups={idx: sorted(slots) for idx, slots in sorted(nominal.items())},
                retained_groups={idx: sorted(slots) for idx, slots in sorted(retained.items())},
                removed={key: assignment[key] for key in sorted(failures)},
                repair_counts=counts, predictive_components=predicted, endpoints_east_north_km=endpoints,
                residual_degrees_of_freedom=repair["residual_degrees_of_freedom"],
                nominal_nuisance_width=counts["curved"][0]-counts["curved"][1]-repair["residual_degrees_of_freedom"]-2,
                curve_allowance=floor(counts["curved"][0]/20))


def audit():
    assets = {path: checked(path, pin) for path, pin in PINS.items()}
    score = json.loads(assets[CONTROL / "score.json"])
    clock = json.loads(assets[CONTROL / "process.json"])
    witness = json.loads(assets[CONTROL / "candidate/exact-named-raw-witness.json"])
    if (score["case"] != "DS30-0220" or score["waveform_reads"] != 0 or not score["terminal_exact"]
            or not all(score["exact_owner_map"].values()) or clock["exit_code"] or clock != score["process"]):
        raise ValueError("Expected the authenticated parity-matched full-detector comparison")
    risk = witness["ports"]["history_risk"]
    attempt, = risk["lean_attempts"]
    half = witness["evidence"]["detail"]["region"]["width_km"]/2
    predicates = reconstruct(risk, half)
    if not all(predicates["passed"].values()):
        raise ValueError(f"An unchanged repair veto still applies: {predicates['passed']}")
    fallback = attempt["fallback_clocks"]
    old = {clock: score["process"][clock] for clock in ("elapsed_s", "cpu_s")}
    return dict(case="DS30-0220", predicate_proof=predicates, current=old, gross_fallback_ceiling=fallback,
                unchanged_cost_floor={k: old[k]-fallback[k] for k in old},
                first_pair=attempt["finish_clocks"], cap_screen=attempt["repair_prepare_clocks"],
                raw_timing_credit=0, waveform_reads=0, solver_workers=0,
                sources={str(path): pin for path, pin in PINS.items()})


class WorkBudget:
    def __init__(self, ordinary):
        self.ordinary = ordinary
        self.over_cap_counts = None

    def admit(self, counts):
        if self.ordinary(counts):
            return True
        if self.over_cap_counts is not None or counts["tracks"][1] <= 0:
            return False
        self.over_cap_counts = dict(counts)
        return True
