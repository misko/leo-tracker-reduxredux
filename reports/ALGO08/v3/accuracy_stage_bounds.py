"""Which measured candidate stages could close the gap while keeping v3's error coverage?"""

from fractions import Fraction
import gzip
import json
from pathlib import Path
from statistics import median

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
    if not 0 <= reduction <= 1 or short["short_cpu"] < 0:
        raise ValueError("Expected a nonnegative callback time and a reduction between zero and one")
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
    paired_ratio = median(Fraction(b if route & (1 << i) else a, a) for i, (a, b) in enumerate(clocks))
    return dict(feasible=result, proof=proof, lower_time_units=lower_time, upper_summed_speedup=baseline/lower_time,
                exact_sum=lower_time == result["total_units"],
                paired_ratio_exact=str(paired_ratio),
                both_gates_met_by_witness=2*result["total_units"] <= baseline and 2*paired_ratio <= 1)


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


def fallback_bound(pairs, candidate_credit, rows, percent):
    """Reduce only the chosen fallback's cost. The comparator stays the measured ALGO08v3."""
    baseline = [stock["wall_units"] for stock, _ in pairs]
    fallback = [time - time*percent//100 for time in baseline]
    candidate = [new["wall_units"] - credit for (_, new), credit in zip(pairs, candidate_credit, strict=True)]
    if any(t < 0 for t in candidate) or not 0 <= percent <= 100:
        raise ValueError("A stage transfer cannot give negative paid time")
    mask, proof = certified_route([a-b for a,b in zip(fallback, candidate, strict=True)], rows)
    chosen = [b if mask & (1 << i) else a for i, (a,b) in enumerate(zip(fallback, candidate, strict=True))]
    median_ratio = median(Fraction(t, ref) for t, ref in zip(chosen, baseline, strict=True))
    return dict(lower_time_units=sum(fallback)-proof["upper_gain"],
                feasible=dict(total_units=sum(chosen), installed_total_units=sum(baseline),
                              paired_ratio_exact=str(median_ratio), candidate_mask=mask),
                both_gates_met_by_witness=2*sum(chosen) <= sum(baseline) and 2*median_ratio <= 1, proof=proof)


def fast_count(pairs, savings, rows):
    """Maximum number of half-time candidates that can be used while retaining the required coverage."""
    weights = [int(2*(candidate["wall_units"] - save) <= stock["wall_units"])
               for (stock,candidate), save in zip(pairs, savings, strict=True)]
    mask, proof = certified_route(weights, rows)
    return dict(available=sum(weights), candidate_mask=mask, attained=proof["gain"],
                maximum=proof["upper_gain"], proof=proof)


def run():
    def read(name):
        return json.loads(gzip.decompress(checked(DATA/name, "sha256:"+SOURCES[name])))

    field = read("ds30-routing-first64.json.gz")
    producer = read("first64-producer-transfer.json.gz")
    costs = {r["case"]:r for r in producer["rows"]}
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
    inputs = producer["alternatives"]["0049_slots_first_bytes"]["individual"]
    buffer_credit = {row["case"]:round(Fraction(str(item["producer_cpu_if_wall"]))*scale)
                     for row,item in zip(producer["rows"], inputs, strict=True)}
    profiles = {"measured_mixed": [0]*len(pairs), "kernel_and_buffer": [], "native_solver_and_buffer": []}
    for case, parts in zip(cases, credits, strict=True):
        profiles["kernel_and_buffer"].append(parts["transferred_kernel"] + buffer_credit[case])
        # 1.5x all native, 1.4x solver; price only buffers outside the native callback.
        profiles["native_solver_and_buffer"].append(parts["free_native"]//3 + 2*parts["free_solver"]//7 + buffer_credit[case])
    rows = constraints(coverage(pairs, None))
    fallback = {name: percent_bracket(lambda p: fallback_bound(pairs, savings, rows, p))
                for name,savings in profiles.items()}
    for name, interval in fallback.items():
        interval["fast_candidates"] = fast_count(pairs, profiles[name], rows)
        interval["half_time_fallback"] = fallback_bound(pairs, profiles[name], rows, 50)
    partitions = {}
    for name, subset in (("first30", slice(0, 30)), ("next34", slice(30, 64))):
        part = pairs[subset]
        groups = coverage(part, None)
        clocks = [(a["wall_units"], b["wall_units"]-c["free_short_and_solver"])
                  for (a,b),c in zip(part, credits[subset], strict=True)]
        partitions[name] = dict(cases=cases[subset], free_short_and_solver=bound(part, clocks, groups, scale),
                                fast_candidates=fast_count(part, profiles["native_solver_and_buffer"][subset],
                                                           constraints(groups)))
    return dict(sources=SOURCES, wall_units_per_second=scale, short_cpu_reduction=str(reduction),
                cases=cases, result=result, required_stage_cuts=brackets, required_installed_cuts=fallback,
                chronological_partitions=partitions)


if __name__ == "__main__":
    print(json.dumps(run(), allow_nan=False, indent=2))
