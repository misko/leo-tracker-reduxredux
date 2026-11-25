"""Score a half-bin-limited CFO change from a genuinely target-masked forecast."""

import argparse
from collections import Counter
from math import ceil, isfinite, remainder, sqrt
import json
from pathlib import Path
import re
from statistics import fmean
import sys

from . import odd_short_interpolation as odd
from .calibration_transport import FIELD, FIRST30, signed_attempt
from .track_cfo_denoise import graph_pins, original_pairs
from directed_donor import arrival_phase


SOURCE = Path(__file__)
PROTOCOL = SOURCE.with_name("held-short-cfo-shrink-protocol.md")
BASELINE = odd.HERE/"measurements/odd-short-interpolation-plan.json.gz"
BASELINE_PIN = "f7c721cd320c0b002b999aff47a2b47b930a7143832e32bef7eb3bf593af11fc"
FULL_BUILD = Path("/tmp/leo-algo08v2-2x-bench/receiver-fractional-exact-v1")
FULL_BUILD_PIN = "5566ddd22345982e1b7673c7d65a8ce5799ce8229275365e1e6e237ab3f0e86d"
FULL_DSO = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
HEADER = odd.signed.RELEASE/"tools/pipeline_eval/variants/portable_fine.h"
HEADER_PIN = "e4a93a37dbaadce0ed94f297d7540c7a29c51fb17dc901582a09e980eb604f89"
DEVELOPMENT = tuple(odd.CASES)
TRANSFER = ("DS30-0019", "DS30-0274")
CASES = DEVELOPMENT + TRANSFER
BIN_HZ = 10_000_000 / (44*512)
PASS, CFO_MISS, ARRIVAL_MISS = "original_joint_pass", "original_cfo_miss", "original_arrival_only_miss"


def checked_bytes(path, expected):
    body = path.read_bytes()
    if odd.signed.tag(body) != "sha256:"+expected.removeprefix("sha256:"):
        raise ValueError(f"Original source bytes changed at {path}")
    return body


def source_contract():
    build = odd.signed.document(FULL_BUILD/"build.json", FULL_BUILD_PIN)
    if build["exact_sha256"] != odd.signed.FULL:
        raise ValueError("The verified residual grid belongs to a different detector")
    checked_bytes(FULL_DSO, odd.signed.FULL)
    source = checked_bytes(FULL_BUILD/"portable_verifier.c", build["verifier_source_sha256"]).decode()
    header = checked_bytes(HEADER, HEADER_PIN).decode()
    fields = (int(re.search(r"glrt_size = ([0-9]+)", source)[1]),
              int(re.search(r"double rate = ([0-9]+)\.0", source)[1]),
              int(re.search(r"PORTABLE_FINE_TAPS = ([0-9]+)", header)[1]))
    if (fields != (512, 10_000_000, 44)
            or "symbol*taps + offset + 21.5) / rate" not in source
            or "steps[frame*63 + symbol - 1] = next - previous" not in source
            or "(1.0/(glrt_size*median))" not in source):
        raise ValueError("Original signed residual-frequency convention changed")
    return dict(full_library=odd.signed.FULL, full_build=FULL_BUILD_PIN, verifier=build["verifier_source_sha256"],
                pilot_header=HEADER_PIN, glrt_bins=fields[0], adc_hz=fields[1], pilot_symbol_samples=fields[2],
                bin_hz=BIN_HZ, half_cap_hz=BIN_HZ/2)


def custody():
    baseline = odd.signed.document(BASELINE, BASELINE_PIN)
    if (baseline["sources"] != odd.source_pins() or set(baseline["cases"]) != set(DEVELOPMENT)
            or baseline["track_configuration"] != odd.signed.PINS["assets/tracks.json"]):
        raise ValueError("Original masked forecast archive has a different rule or Graph")
    return baseline, dict(archived_predictions=BASELINE_PIN, odd_sources=baseline["sources"],
                          ledger=FIRST30, graph_configuration=baseline["track_configuration"],
                          residual_grid=source_contract(), protocol=odd.signed.tag(PROTOCOL.read_bytes()),
                          source=odd.signed.tag(SOURCE.read_bytes()))


def worker(case, role, pairs):
    if case in DEVELOPMENT:
        return odd.original(case, role)
    entry = pairs[case, role]
    pair_path = FIELD/"cases"/case/"pair.json"
    body = pair_path.read_bytes()
    pair = json.loads(body)
    if (pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]
            or pair["generation"] != entry["generation"] or pair["actual_order"] != entry["actual_order"]
            or entry["attempt_result_sha256"] != pair["attempt_result_sha256"][role]):
        raise ValueError("Prospective worker differs from the frozen original pair")
    return pair, signed_attempt(FIELD, entry), (FIELD/entry["attempt"]).parent/"publication"


def candidate_inputs(case, pairs):
    pair, result, pub = worker(case, "successor", pairs)
    identity = result["raw_identity"]
    raw = odd.signed.document(pub/"unified-short-bootstrap.json")
    native, _, _ = odd.signed.qualified_candidate(pub, raw, result["native_sha256"], identity["region_sha256"])
    aperture = raw["held_anchor_route"]["receiver_recipe"]
    rx = raw["receiver_audit"]
    if (aperture["rule"] != odd.SOURCE_RECIPE or aperture["streams"] != list(odd.STREAM)
            or rx["recording_authority"] != identity["raw_authority_sha256"]
            or native["source"]["input_manifest_sha256"] != identity["inventory_sha256"]
            or native["source"]["session_id"] != identity["session_id"]):
        raise ValueError("Measured packet violates original RF and aperture custody")
    masked, held, modes = odd.mask(native)
    if modes != rx["native"]["native_calls"]:
        raise ValueError("Held schedule changed original calls")
    return pair, result, native, masked, held, modes


def shrink(measured, forecast):
    """Use a direct signed comparison on the donor lift, with no wrapping."""
    delta = forecast-measured
    if not isfinite(delta) or abs(delta) > BIN_HZ:
        return None
    return measured + delta/2


def nominate_changes(held, original, forecasts):
    if not forecasts.keys() <= held.keys():
        raise ValueError("A forecast escaped the pre-masked target set")
    eligible, counts = {}, Counter()
    for oid, forecast in forecasts.items():
        target = original[oid]
        if not target["short"]:
            raise ValueError("Masked short target is a full anchor")
        ids = forecast["donors"]
        if len(ids) != 2 or any(donor in held for donor in ids):
            raise ValueError("An unmeasured visit was used as a donor")
        donors = [original[donor] for donor in ids]
        lane = held[oid]["lane"]
        if any(tuple(row["row"][k] for k in odd.LANE) != lane or row["factor"] is None for row in donors):
            raise ValueError("Donors lack original measured same-lane support")
        if type(forecast["graph_alias_lift"]) is not int:
            raise ValueError("The donors did not specify one signed branch")
        left, right = (dict(row, lift=forecast["graph_alias_lift"]) for row in donors)
        predicted, reason = odd.interpolate(left, target["counter"], right)
        if predicted != forecast or reason != "proposed":
            raise ValueError("Sealed forecast differs from the same-lift straddlers")
        factor = target["factor"]
        if factor is None:
            counts["target_empty"] += 1
            continue
        value = factor[odd.HERTZ]
        new = shrink(value, forecast["cfo_hz"])
        if new is None:
            counts["more_than_one_bin"] += 1
            continue
        counts["eligible"] += 1
        eligible[oid] = dict(original_hz=value, forecast_hz=forecast["cfo_hz"], updated_hz=new,
                             arrival=arrival_phase(target["counter"], factor))
    return eligible, dict(counts)


def predict(snapshot):
    baseline, pins = custody()
    pairs = original_pairs(snapshot, "held")
    inputs = {case: candidate_inputs(case, pairs) for case in CASES}
    graph_pins()
    forecasts, evidence = {}, {}
    for case, (pair, result, native, masked, held, modes) in inputs.items():
        receipt = dict(native_sha256=result["native_sha256"], masked_sha256=odd.signed.canonical(masked),
                       held_order_sha256=odd.signed.canonical(list(held)), held_lanes=len(held))
        if case in DEVELOPMENT:
            frozen = baseline["cases"][case]
            if any(frozen[k] != v for k, v in receipt.items()):
                raise ValueError("Archived forecasts do not bind the enrolled pre-masked packet")
            forecasts[case], scope, eligibility = (frozen[k] for k in ("proposals", "graph", "eligibility"))
        else:
            retained = odd.signed.opportunities(masked)
            graph, _, scope = odd.signed.graph(masked, retained)
            if graph.keys() & held.keys():
                raise ValueError("Held lane reached Graph")
            forecasts[case], eligibility = odd.nominate(held, retained, graph)
        evidence[case] = receipt | dict(graph=scope, graph_forecast_eligibility=eligibility,
                                        native_calls=modes, original_pair=odd.signed.canonical(pair))
    # The forecasts are complete before selecting even one original held winner.
    for case, (_, _, native, _, held, _) in inputs.items():
        original = odd.signed.opportunities(native)
        eligible, gates = nominate_changes(held, original, forecasts[case])
        evidence[case] |= dict(held_candidate_positives=sum(original[oid]["factor"] is not None for oid in held),
                               forecasts=forecasts[case], eligible=eligible, residual_gates=gates)
    return dict(schema="held-short-cfo-shrink-v1", pins=pins, cases=evidence)


def aligned_errors(original, reference, proposed):
    measured, stock = original["factor"], reference["factor"]
    if measured is None:
        raise ValueError("A shrink requires an original measured signed winner")
    counter = original["counter"]
    arrival = arrival_phase(counter, measured)
    if proposed["arrival"] != arrival or proposed["original_hz"] != measured[odd.HERTZ]:
        raise ValueError("The selected measurement's arrival or signed CFO changed before scoring")
    if proposed["updated_hz"] != shrink(measured[odd.HERTZ], proposed["forecast_hz"]):
        raise ValueError("The sealed update differs from the frozen bounded rule")
    if stock is None:
        return None
    return (measured[odd.HERTZ]-stock[odd.HERTZ], proposed["updated_hz"]-stock[odd.HERTZ],
            abs(remainder(arrival-arrival_phase(counter, stock), odd.PERIOD)))


def metrics(values):
    if not values:
        return None
    magnitude = sorted(map(abs, values))
    return dict(bias_hz=fmean(values), rms_hz=sqrt(fmean(x*x for x in values)), mae_hz=fmean(magnitude),
                p95_absolute_hz=magnitude[ceil(.95*len(magnitude))-1], max_absolute_hz=magnitude[-1])


def evaluate(rows, missing):
    result = {}
    for hz, samples in odd.WINDOWS:
        counts = Counter({key: 0 for key in (PASS, CFO_MISS, ARRIVAL_MISS, "closer", "farther", "tied",
                                              "cfo_restored", "cfo_spoiled", "joint_restored", "joint_spoiled")})
        for x, y, clock in rows:
            before, after, arrival = abs(x) <= hz, abs(y) <= hz, clock <= samples
            category = CFO_MISS if not before else PASS if arrival else ARRIVAL_MISS
            direction = "closer" if abs(y) < abs(x) else "farther" if abs(y) > abs(x) else "tied"
            counts[category] += 1
            counts[direction] += 1
            counts[f"{category}_{direction}"] += 1
            counts["cfo_restored"] += not before and after
            counts["cfo_spoiled"] += before and not after
            counts["joint_restored"] += not before and after and arrival
            counts["joint_spoiled"] += before and not after and arrival
        result[f"{hz}Hz_{samples}samples"] = dict(**counts, joint_before=counts[PASS],
                                                  joint_after=counts[PASS]+counts["joint_restored"]-counts["joint_spoiled"])
    return dict(scored=len(rows), installed_empty=missing, eligible=len(rows)+missing,
                original=metrics([x for x, _, _ in rows]), shrunk=metrics([y for _, y, _ in rows]), windows=result)


def score(snapshot, plan_path, pin):
    plan = odd.signed.document(plan_path, pin)
    _, pins = custody()
    if plan["pins"] != pins or set(plan["cases"]) != set(CASES):
        raise ValueError("Score requires the frozen four-record candidate-only forecast")
    pairs = original_pairs(snapshot, "held")
    cases, pooled, pooled_missing = {}, [], 0
    for case in CASES:
        sealed = plan["cases"][case]
        pair, candidate, native, masked, held, modes = candidate_inputs(case, pairs)
        if (sealed["native_sha256"] != candidate["native_sha256"] or sealed["original_pair"] != odd.signed.canonical(pair)
                or sealed["masked_sha256"] != odd.signed.canonical(masked)
                or sealed["held_order_sha256"] != odd.signed.canonical(list(held))):
            raise ValueError("Original authenticated candidate membership changed")
        original = odd.signed.opportunities(native)
        eligible, gates = nominate_changes(held, original, sealed["forecasts"])
        if eligible != sealed["eligible"] or gates != sealed["residual_gates"]:
            raise ValueError("New decisions differ from the independently sealed shrinkages")
        stock_pair, installed, pub = worker(case, "installed", pairs)
        if stock_pair != pair or installed["raw_identity"] != candidate["raw_identity"]:
            raise ValueError("Full and short packets use different raw observations or offers")
        stock = odd.signed.read_native(pub, installed["native_sha256"])
        if stock["provenance"]["detector_sha256"] != "sha256:"+odd.signed.FULL:
            raise ValueError("Reference is not the original complete-aperture detector")
        reference = odd.signed.opportunities(stock)
        odd.signed.bind_pair(stock, native, reference, original)
        values = [aligned_errors(original[oid], reference[oid], item) for oid, item in eligible.items()]
        rows = [value for value in values if value is not None]
        missing = len(values)-len(rows)
        cases[case] = evaluate(rows, missing) | dict(installed_sha256=installed["native_sha256"],
            candidate_sha256=candidate["native_sha256"], held_lanes=len(held),
            held_candidate_positives=sealed["held_candidate_positives"], forecast_count=len(sealed["forecasts"]),
            changed=sum(x["original_hz"] != x["updated_hz"] for x in eligible.values()),
            max_abs_change_hz=max((abs(x["updated_hz"]-x["original_hz"]) for x in eligible.values()), default=0.),
            residual_gates=gates, native_calls=modes,
            apertures=dict(Counter(str(sum(sealed["forecasts"][oid]["donor_full"])) for oid in eligible)))
        if case in TRANSFER:
            pooled.extend(rows)
            pooled_missing += missing
    return dict(prediction_sha256=pin, residual_grid=pins["residual_grid"], cases=cases,
                pooled_transfer=evaluate(pooled, pooled_missing),
                waveform_reads=0, orbit_reads=0, solver_launches=0, graph_rebuilds_in_score=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--score", nargs=2, metavar=("SEALED_PLAN", "SHA256"))
    args = parser.parse_args()
    sys.addaudithook(odd.deny_backing)
    if args.score:
        path, pin = args.score
        result = score(args.snapshot, Path(path), pin)
    else:
        sys.addaudithook(odd.deny_installed_outcomes)
        result = predict(args.snapshot)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
