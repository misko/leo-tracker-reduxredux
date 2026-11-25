"""Give the 39 archived South spacing failures a perfect spacing pass."""

import argparse
from collections import Counter
import json
from math import isfinite, remainder
from pathlib import Path
import sys
from unittest.mock import patch

from . import held_short_cfo_shrink_south as old


odd, shrink, signed = old.odd, old.shrink, old.signed
ORIGINAL_INTERPOLATE = odd.interpolate
PROTOCOL = Path(__file__).with_name("south-spacing-ceiling-protocol.md")
SAVED_PRIOR = odd.HERE / "measurements/held-short-cfo-shrink-south-prediction.json.gz"
PRIOR_PIN = "5fb3dd380c1f5de22e78d727d449dd5fcaa8bd4287414c746ad600791124f6f3"


def spacing_pass(left, middle, right):
    """Keep the frozen interpolation operands and all guards after spacing."""
    a, b = middle - left["counter"], right["counter"] - middle
    if not (a > 0 and b > 0):
        raise ValueError("A chronological straddle is required even for a perfect spacing pass")
    if left["lift"] != right["lift"]:
        return None, "ambiguous_alias_branch"
    lift = left["lift"]
    native_a, native_b = (row["factor"][odd.HERTZ] for row in (left, right))
    lifted_a, lifted_b = (frequency + lift * signed.ALIAS for frequency in (native_a,native_b))
    if abs(lifted_b - lifted_a) * odd.ADC > 8_000 * (a+b):
        return None, "slope"
    start, end = (odd.arrival_phase(row["counter"],row["factor"]) for row in (left,right))
    delta = remainder(end-start,odd.PERIOD)
    if not isfinite(delta) or abs(delta) == odd.PERIOD/2:
        return None, "ambiguous_arrival_arc"
    fraction = a/(a+b)
    lifted = lifted_a + fraction * (lifted_b-lifted_a)
    return dict(cfo_hz=lifted-lift*signed.ALIAS,lifted_cfo_hz=lifted,graph_alias_lift=lift,
                arrival=(start+fraction*delta)%odd.PERIOD,donors=[left["id"],right["id"]],
                donor_counters=[left["counter"],right["counter"]],
                donor_full=[not row["short"] for row in (left,right)],
                left_wait_samples=a,right_wait_samples=b), "proposed"


def spacing_only(left, middle, right):
    forecast, reason = ORIGINAL_INTERPOLATE(left,middle,right)
    return spacing_pass(left,middle,right) if reason == "spacing" else (forecast,reason)


def forecast(saved, held, retained, graph):
    before, reasons = odd.nominate(held,retained,graph)
    if before != saved["proposals"] or reasons != saved["release_forecast_eligibility"] or before:
        raise ValueError("The unchanged release nomination must reproduce the sealed baseline")
    by_radio_clock = {(target["lane"][-1],target["counter"]):oid for oid,target in held.items()}
    spacing = {}

    def audit(left, middle, right):
        choice, reason = ORIGINAL_INTERPOLATE(left,middle,right)
        if reason != "spacing":
            return choice,reason
        oid = by_radio_clock[left["row"]["receiver_id"],middle]
        if oid in spacing:
            raise ValueError("A held opportunity received conflicting spacing records")
        prediction, secondary = spacing_pass(left,middle,right)
        spacing[oid] = dict(left_id=left["id"],right_id=right["id"],left_samples=middle-left["counter"],
                            right_samples=right["counter"]-middle,after_spacing=secondary)
        return prediction,secondary

    with patch.object(odd,"interpolate",audit):
        proposed, waterfall = odd.nominate(held,retained,graph)
    if len(spacing) != reasons["spacing"] or not proposed.keys() <= spacing.keys():
        raise ValueError("Perfect spacing can only reach the archived spacing failures")
    return spacing,proposed,waterfall


def prepare():
    saved,native,offers,pins = old.candidates()
    prior = signed.document(SAVED_PRIOR,PRIOR_PIN)
    masked,held,calls = odd.mask(native)
    if (prior["pins"] != pins or prior["offers"] != offers or prior["held_lanes"] != len(held)
            or prior["masked_native_sha256"] != signed.canonical(masked)
            or prior["held_order_sha256"] != signed.canonical(list(held))
            or any(calls != offer["native_calls"] for offer in offers.values())):
        raise ValueError("Need the authentic original selected South Graph input")
    custody = dict(prior_prediction_sha256=PRIOR_PIN,protocol_sha256=signed.tag(PROTOCOL.read_bytes()),
                   source_sha256=signed.tag(Path(__file__).read_bytes()),historical_pins=pins)
    return saved,native,masked,held,prior,custody


def edits(held, original, spacing, proposals):
    with patch.object(odd,"interpolate",spacing_only):
        eligible,gates = shrink.nominate_changes(held,original,proposals)
    if not eligible.keys() <= proposals.keys() <= spacing.keys():
        raise ValueError("A perfect spacing pass cannot nominate another lane")
    evidence = {}
    for oid,row in spacing.items():
        positive = original[oid]["factor"] is not None
        reason = (row["after_spacing"] if oid not in proposals else
                  "target_empty" if not positive else "eligible" if oid in eligible else "more_than_one_bin")
        evidence[oid] = dict(row,candidate_positive=positive,final_gate=reason)
    return eligible,gates,evidence


def predict():
    _,native,masked,held,prior,pins = prepare()
    shrink.graph_pins()
    retained = signed.opportunities(masked)
    graph,_,scope = signed.graph(masked,retained)
    if scope != prior["graph"] or graph.keys() & held.keys():
        raise ValueError("The same target-excluded selected-packet Graph is required")
    spacing,proposals,waterfall = forecast(prior,held,retained,graph)
    original = signed.opportunities(native)
    eligible,gates,evidence = edits(held,original,spacing,proposals)
    return dict(pins=pins,baseline_waterfall=prior["release_forecast_eligibility"],graph=scope,
                held_lanes=len(held),held_candidate_positive=sum(original[k]["factor"] is not None for k in held),
                spacing_failures=evidence,forecasts=proposals,waterfall=waterfall,edit_gates=gates,eligible=eligible)


def unchanged_pair(counter, original, reference):
    x,y = original[odd.HERTZ],reference[odd.HERTZ]
    a,b = (odd.arrival_phase(counter,factor) for factor in (original,reference))
    return x-y,x-y,abs(remainder(a-b,odd.PERIOD))


def score(plan, pin):
    saved,native,_,held,prior,pins = prepare()
    original = signed.opportunities(native)
    spacing = plan["spacing_failures"]
    forecasts = plan["forecasts"]
    eligible,gates,evidence = edits(held,original,spacing,forecasts)
    if (plan["pins"] != pins or plan["graph"] != prior["graph"] or len(held) != plan["held_lanes"]
            or evidence != spacing or eligible != plan["eligible"] or gates != plan["edit_gates"]
            or len(evidence) != prior["release_forecast_eligibility"]["spacing"]):
        raise ValueError("Require the sealed perfect-spacing experiment with its original custody")
    stock,offers = old.stock_reference(saved)
    reference = signed.opportunities(stock)
    signed.bind_pair(stock,native,reference,original)
    values = [shrink.aligned_errors(original[oid],reference[oid],record) for oid,record in eligible.items()]
    paired = [record for record in values if record is not None]
    annotated = [unchanged_pair(original[oid]["counter"],original[oid]["factor"],reference[oid]["factor"])
                 for oid in held.keys()-eligible.keys()
                 if original[oid]["factor"] is not None and reference[oid]["factor"] is not None]
    present = sum(original[k]["factor"] is not None for k in held)
    scope = {name:dict(Counter(record["final_gate"] for record in evidence.values()
                             if record["candidate_positive"] is positive))
             for name,positive in (("candidate_positive",True),("candidate_empty",False))}
    return dict(candidate_plan_sha256=pin,reference_offers=offers,held_lanes=len(held),held_candidate_positive=present,
                held_installed_positive=sum(reference[k]["factor"] is not None for k in held),
                spacing_waterfall_by_candidate_presence=scope,spacing_test_installed_positive=sum(
                    reference[oid]["factor"] is not None for oid in spacing),
                edits_changed=sum(x["original_hz"] != x["updated_hz"] for x in eligible.values()),
                eligible_outcomes=shrink.evaluate(paired,len(values)-len(paired)),
                all_held_candidate_positive=shrink.evaluate(paired+annotated,present-len(paired)-len(annotated)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score",nargs=2,metavar=("PLAN","SHA256"))
    args = parser.parse_args()
    sys.addaudithook(odd.deny_backing)
    if args.score:
        path,pin = args.score
        result = score(signed.document(Path(path),pin),pin)
    else:
        def candidate_only(event,params):
            if event == "open" and isinstance(params[0],(str,bytes)):
                from os import fsdecode

                path = Path(fsdecode(params[0])).resolve()
                if path.is_relative_to(old.SAVED_STOCK) or path == old.south.NAMED:
                    raise ValueError("The spacing diagnostic cannot open installed outcomes before sealing")

        sys.addaudithook(candidate_only)
        result = predict()
    print(json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False))
