"""Which measured candidate stages could close the gap while keeping v3's error coverage?"""

from fractions import Fraction
import gzip
import json
from pathlib import Path

from .ds30_oracle_routing import checked, coverage, meets
from .ds30_routing_first64 import certified_route, constraints, summary


DATA = Path(__file__).with_name("measurements")
SOURCES = {
    "ds30-routing-first64.json.gz": "6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10",
    "first64-producer-transfer.json.gz": "122de8ddfdf498f6f372f6f3896387b6ede886b4b136c180aa3e45f4da783c03",
    "short-phase-first64.json.gz": "ee4858211d32ea017a814b827bd8ee8292b0ce204ba62c8bbb1c9580a2131366",
    "short-shared-phase-0016.json.gz": "b88018f36979c7a2fbb32c096c7048666dfa3b1b45e96f323210809e1ee6ffeb",
}


def stages(row, short, reduction, scale):
    def units(key):
        return round(Fraction(str(row[key])) * scale)

    acquisition = units("acquisition_s")
    native = units("native_detector_s")
    solver = units("solver")
    short_wall = round(Fraction(str(short["short_wall"])) * scale)
    if not (0 <= short_wall <= native <= acquisition and 0 <= solver and acquisition + solver <= units("actual_wall_s")):
        raise ValueError("The stage clocks must be nested within the measured attempt")
    short_cpu = Fraction(str(short["short_cpu"])) * scale
    return dict(measured=0, transferred_kernel=min(short_wall, round(short_cpu * reduction)),
                free_short=short_wall, free_native=native, free_nonnative_acquisition=acquisition-native,
                free_solver=solver, free_acquisition=acquisition, free_native_and_solver=native+solver,
                free_short_and_solver=short_wall+solver)


def bound(pairs, clocks, groups, scale):
    route, proof = certified_route([a-b for a,b in clocks], constraints(groups))
    if not meets(groups, route):
        raise ValueError("The chosen assignment misses an accuracy target")
    result = summary(pairs, clocks, groups, route, scale)
    baseline = result["installed_total_units"]
    lower_time = baseline - proof["upper_gain"]
    if not 0 < lower_time <= result["total_units"]:
        raise ValueError("Invalid certified timing bound")
    return dict(feasible=result, proof=proof, lower_time_units=lower_time, upper_summed_speedup=baseline/lower_time,
                exact_sum=lower_time == result["total_units"],
                both_gates_met_by_witness=2*result["total_units"] <= baseline and result["median_paired_wall_ratio"] <= .5)


def percent_bracket(evaluate):
    """Bound the sum gate on integer percentages; retain the independent median check."""
    low, high = 0, 100
    while high - low > 1:
        middle = (high + low) // 2
        trial = evaluate(middle)
        baseline = trial["feasible"]["installed_total_units"]
        if 2 * trial["lower_time_units"] > baseline:
            low = middle
        elif 2 * trial["feasible"]["total_units"] <= baseline:
            high = middle
        else:
            raise ValueError("The certificate cannot decide this percentage")
    previous, passing = evaluate(low), evaluate(high)
    if (2*previous["lower_time_units"] <= previous["feasible"]["installed_total_units"] or
            2*passing["feasible"]["total_units"] > passing["feasible"]["installed_total_units"]):
        raise ValueError("The percentage interval does not bracket a crossing")
    return dict(previous_percent=low, previous=previous, passing_percent=high, passing=passing)


def run():
    def read(name):
        return json.loads(gzip.decompress(checked(DATA/name, "sha256:"+SOURCES[name])))

    field = read("ds30-routing-first64.json.gz")
    costs = {r["case"]:r for r in read("first64-producer-transfer.json.gz")["rows"]}
    calls = {r["case"]:r for r in read("short-phase-first64.json.gz")["rows"]}
    donor = read("short-shared-phase-0016.json.gz")["result"]
    old, new = (donor[k]["receiver_audit"]["native"]["native_cpu_ns"]["short_primary"]
                for k in ("historical_control", "candidate"))
    reduction = 1-Fraction(new, old)
    scale = field["result"]["clock_unit_denominator"]
    pairs, credits = [], []
    cases = [r["case"] for r in field["measurements"]]
    if len(cases) != 64 or len(set(cases)) != 64 or set(cases) != set(costs) or set(cases) != set(calls):
        raise ValueError("Unmatched first-64 rosters")
    for r in field["measurements"]:
        case = r["case"]
        stock, cand = (r[k] | {"case":case} for k in ("installed","successor"))
        cost = costs[case]
        if (cost["pins"]["result"] != cand["attempt_result_sha256"] or cost["stock_result"] != stock["attempt_result_sha256"]
                or cost["actual_wall_s"] != cand["elapsed_s"] or calls[case]["actual_wall_s"] != cand["elapsed_s"]):
            raise ValueError("The cost and accuracy receipts identify different attempts")
        pairs.append((stock, cand))
        credits.append(stages(cost, calls[case], reduction, scale))
    result, brackets = {}, {}
    for name, cuts in (("one_and_two_km", [1.,2.]), ("every_threshold", None)):
        groups = coverage(pairs, cuts)
        def evaluate(scope, percent):
            clocks = [(a["wall_units"], b["wall_units"]-saving[scope]*percent//100)
                      for (a,b),saving in zip(pairs,credits,strict=True)]
            return bound(pairs, clocks, groups, scale)
        result[name] = {scope:evaluate(scope, 100) for scope in credits[0]}
        brackets[name] = {}
        for scope in ("free_acquisition", "free_native_and_solver"):
            brackets[name][scope] = percent_bracket(lambda percent: evaluate(scope, percent))
    return dict(sources=SOURCES, wall_units_per_second=scale, short_cpu_reduction=str(reduction),
                cases=cases, result=result, required_stage_cuts=brackets)


if __name__ == "__main__":
    print(json.dumps(run(), allow_nan=False, indent=2))
