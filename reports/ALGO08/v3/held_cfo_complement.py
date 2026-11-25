"""Replicate the frozen CFO feature on the complementary nonanchor visits."""

import argparse
from collections import Counter
import json
from math import isfinite, remainder
from pathlib import Path
import sys

from leo.analysis.localization_v3.tracks import winning_observations
from leo.analysis.polynomial_tracklets import TrackConfig

from . import held_cfo_features as stage
from . import held_cfo_features_trial as trial
from . import held_short_cfo_shrink as scoring
from . import odd_short_interpolation as odd
from .track_cfo_denoise import graph_pins, original_pairs
from directed_donor import arrival_phase


PROTOCOL = Path(__file__).with_name("held-cfo-complement-protocol.md")
STAGE_PIN = "65a9934437d2d495b269f7377dd4d82ebe4d4e1e6f6b8e3e89717f89a25e8843"
SCORE_PIN = "2ac33ded7301abb66c49661a4eb9e24c7fdc9582731d0bc66df383c1a9e1d279"
ODD_SCORE = odd.HERE / "measurements/held-short-cfo-shrink-score.json.gz"
ODD_SCORE_PIN = "2c2e083b3d825e0ff97e1dbbe6f9807327c26dd173486017dcbabd6feb1e13ca"
CASES = tuple(trial.CASES)
TARGET_POSITIONS = (2, 4, 6)


def masked_even(native):
    source, proof = native["source"], native["provenance"]
    session = source["session_id"]
    sequence, last = Counter(), {}
    targets, retained, anchors, visits, masked = {}, {}, set(), [], []
    rows = source["probes"]
    for left, right in zip(rows[::2], rows[1::2], strict=True):
        stream = tuple(left[name] for name in stage.STREAM)
        counter, visit = left["valid_start_counter"], left["visit_index"]
        if ([left["receiver_id"], right["receiver_id"]] != [0, 1]
                or any(left[name] != right[name] for name in stage.STEREO_FIELDS)
                or stream in last and last[stream] >= counter):
            raise ValueError("Expected the original ordered stereo opportunities")
        position = sequence[stream] % 8
        sequence[stream] += 1
        last[stream] = counter
        visits.append(visit)
        for row in (left, right):
            radio = row["receiver_id"]
            oid = stage.tag(f"{session}:{radio}:{counter}".encode())
            if oid in targets or oid in retained:
                raise ValueError("Repeated signed stereo opportunity")
            lane = dict(id=oid, counter=counter, short=position != 0, row=row, lane=(*stream,radio))
            if position in TARGET_POSITIONS:
                targets[oid] = lane
                masked.append(dict(row,candidates=[]))
            else:
                if position == 0:
                    anchors.add(oid)
                retained[oid] = dict(lane,factor=stage.winner(row))
                masked.append(row)
    excluded = [row["visit"] for row in proof["excluded_windows"]]
    if (visits != sorted(visits) or sorted(visits+excluded) != list(range(proof["window_count"]))
            or len(visits) != proof["processed_windows"]):
        raise ValueError("Admitted and excluded visits must partition the signed acquisition")
    digest = odd.signed.canonical(["cancellation",source["raw_recording_authority_digest"],
                                   proof["detector_sha256"][7:],masked])
    packet = dict(native,source=dict(source,probes=masked,analysis_manifest_sha256=digest),
                  provenance=dict(proof,run_id="even-short-graph-"+digest[7:39]))
    return packet, targets, retained, anchors


def verify_overlay(native, features, anchors):
    original, _ = winning_observations(native)
    corrected = stage.apply_to_winners(native,original,features)
    actual, anchor_winners = set(), 0
    for old, new in zip(original,corrected,strict=True):
        oid = old["observation_id"]
        if any(old[k] != new[k] for k in old.keys()-{"measured_cfo_hz"}) or old.keys() != new.keys():
            raise ValueError("A derived observation changed a field outside signed CFO")
        if old["measured_cfo_hz"] != new["measured_cfo_hz"]:
            actual.add(oid)
        anchor_winners += oid in anchors
    if actual & anchors or not actual <= features.edits.keys():
        raise ValueError("An anchor or unproposed winner changed")
    return dict(original_winners=len(original),unchanged_winners=len(original)-len(actual),
                anchor_lanes=len(anchors),anchor_winners=anchor_winners,changed_winners=len(actual),
                corrected_rows_sha256=odd.signed.canonical(corrected))


def bind_sources():
    scoring.checked_bytes(Path(stage.__file__),STAGE_PIN)
    scoring.checked_bytes(Path(scoring.__file__),SCORE_PIN)
    old = odd.signed.document(trial.PLAN,trial.PLAN_PIN)
    pins = dict(stage_sha256=STAGE_PIN,scorer_sha256=SCORE_PIN,graph_config_sha256=trial.CONFIG_PIN,
                prior_odd_plan_sha256=trial.PLAN_PIN,ledger_sha256=scoring.FIRST30,
                protocol_sha256=odd.signed.tag(PROTOCOL.read_bytes()))
    return old, pins


def paired_source(case, pairs):
    pair, result, native, original_masked, odd_held, calls = scoring.candidate_inputs(case,pairs)
    ram_path, native_pin, *_ = trial.CASES[case]
    ram = json.loads(trial.checked_bytes(Path(ram_path),native_pin))
    if native_pin != result["native_sha256"].removeprefix("sha256:") or ram != native:
        raise ValueError("The independently pinned RAM evidence does not match the verified pair")
    return pair, result, ram, original_masked, odd_held, calls


def prepare(case, pairs, old):
    pair, result, native, original_masked, odd_held, calls = paired_source(case,pairs)
    masked, held, retained, anchors = masked_even(native)
    old_case = old["cases"][case]
    if (held.keys() & odd_held.keys() or anchors & odd_held.keys()
            or set(held) | set(odd_held) != set(held) | (retained.keys()-anchors)
            or len(anchors) != calls["full"] or len(held)+len(odd_held) != calls["short_primary"]
            or old_case["native_sha256"] != result["native_sha256"]
            or old_case["masked_sha256"] != odd.signed.canonical(original_masked)
            or old_case["held_order_sha256"] != odd.signed.canonical(list(odd_held))
            or old_case["original_pair"] != odd.signed.canonical(pair)):
        raise ValueError("The complementary fold, full anchors or earlier odd fold do not bind")
    evidence = dict(pair_sha256=old_case["original_pair"],native_sha256=result["native_sha256"],
                    mask_sha256=odd.signed.canonical(masked),held_order_sha256=odd.signed.canonical(list(held)),
                    held_lanes=len(held),anchor_lanes=len(anchors),original_calls=calls,
                    old_odd_held_lanes=len(odd_held),old_odd_target_overlap=0)
    return pair,result,native,masked,held,retained,anchors,evidence


def audited_features(native, held, retained, forecasts, graph, eligibility):
    used = {oid for row in forecasts.values() for oid in row["donors"]}
    if used & held.keys() or not used <= retained.keys():
        raise ValueError("Only retained measured donors can support the complementary fold")
    edits, gates = stage.apply_shrink(held,forecasts)
    checked = scoring.nominate_changes(held,odd.signed.opportunities(native),forecasts)
    if (edits,gates) != checked or not edits.keys() <= held.keys():
        raise ValueError("The released held-winner or original sealed shrink semantics diverged")
    return stage.DerivedCfo(stage.identity(native),edits,graph,forecasts,eligibility,gates), used


def predict(snapshot):
    old, pins = bind_sources()
    graph_pins()
    config = TrackConfig(**json.loads(trial.checked_bytes(trial.CONFIG,trial.CONFIG_PIN))["config"])
    pairs = original_pairs(snapshot,"held")
    cases = {}
    for case in CASES:
        _,_,native,masked,held,retained,anchors,evidence = prepare(case,pairs,old)
        if native["source"]["sample_rate_hz"] != stage.ADC or config.alias_spacing_hz != stage.ALIAS:
            raise ValueError("Signed sample rate or alias scale diverged from the original rule")
        packet = stage.prepare_tracks(masked,config)
        donors = stage.released_donors(packet,retained)
        if donors.keys() & held.keys():
            raise ValueError("Held observations entered the complementary Graph")
        forecasts, eligibility = stage.forecasts_for(held,retained,donors)
        graph = dict(tracks=len(packet["tracks"]),assigned=packet["graph_points"],
                     curved_tracks=len(packet["curved_indices"]))
        features, used = audited_features(native,held,retained,forecasts,graph,eligibility)
        audit = verify_overlay(native,features,anchors)
        cases[case] = evidence | dict(graph=graph,eligibility=eligibility,gates=features.gates,
                                     forecasts=forecasts,edits=features.edits,overlay=audit,
                                     used_donors=len(used),used_anchor_donors=len(used & anchors),
                                     old_odd_edited_rows_used_unmodified=len(used & old["cases"][case]["eligible"].keys()))
    return dict(pins=pins,cases=cases)


def paired_error(original, reference):
    clock = original["counter"]
    before, stock = original["factor"], reference["factor"]
    delta = before[stage.HERTZ] - stock[stage.HERTZ]
    phase = abs(remainder(arrival_phase(clock,before)-arrival_phase(clock,stock),odd.PERIOD))
    if not isfinite(delta) or not isfinite(phase):
        raise ValueError("Need finite original signed paired errors")
    return delta,delta,phase


def metrics(held, edits, original, reference):
    opportunity = Counter(dict.fromkeys(("both_positive","candidate_only","installed_only","both_empty"),0))
    eligible, unchanged = [], []
    missing_eligible = 0
    for oid in held:
        candidate, stock = original[oid], reference[oid]
        if candidate["factor"] is None:
            opportunity["both_empty" if stock["factor"] is None else "installed_only"] += 1
        elif stock["factor"] is None:
            opportunity["candidate_only"] += 1
            missing_eligible += oid in edits
        else:
            opportunity["both_positive"] += 1
            if oid in edits:
                eligible.append(scoring.aligned_errors(candidate,stock,edits[oid]))
            else:
                unchanged.append(paired_error(candidate,stock))
    return (dict(opportunity),eligible,unchanged,missing_eligible)


def score(snapshot, plan, plan_pin):
    old, pins = bind_sources()
    if plan["pins"] != pins or set(plan["cases"]) != set(CASES):
        raise ValueError("Need the sealed complementary two-case plan")
    historical = odd.signed.document(ODD_SCORE,ODD_SCORE_PIN)["cases"]
    pairs = original_pairs(snapshot,"held")
    cases, pooled, pooled_untouched = {}, [], []
    all_missing, eligible_missing = 0, 0
    for case in CASES:
        pair,candidate,native,_,held,retained,anchors,evidence = prepare(case,pairs,old)
        frozen = plan["cases"][case]
        features, used = audited_features(native,held,retained,frozen["forecasts"],frozen["graph"],frozen["eligibility"])
        if (any(frozen[key] != value for key,value in evidence.items())
                or features.edits != frozen["edits"] or features.gates != frozen["gates"]
                or verify_overlay(native,features,anchors) != frozen["overlay"] or len(used) != frozen["used_donors"]):
            raise ValueError("The even-fold score requires its original sealed evidence")
        stock_pair, installed, pub = scoring.worker(case,"installed",pairs)
        if pair != stock_pair or installed["raw_identity"] != candidate["raw_identity"]:
            raise ValueError("Reference acquisition, original offer or reference generation changed")
        stock = odd.signed.read_native(pub,installed["native_sha256"])
        if stock["provenance"]["detector_sha256"] != "sha256:"+odd.signed.FULL:
            raise ValueError("Expected the installed full detector")
        original, reference = map(odd.signed.opportunities,(native,stock))
        odd.signed.bind_pair(stock,native,reference,original)
        opportunity, eligible, unchanged, missing = metrics(held,features.edits,original,reference)
        old_score = historical[case]
        if old_score["installed_sha256"] != installed["native_sha256"] or old_score["candidate_sha256"] != candidate["native_sha256"]:
            raise ValueError("The descriptive odd fold uses different original packets")
        cases[case] = dict(installed_sha256=installed["native_sha256"],opportunities=opportunity,**evidence,
                           forecast_count=len(frozen["forecasts"]),gates=features.gates,overlay=frozen["overlay"],
                           used_donors=frozen["used_donors"],used_anchor_donors=frozen["used_anchor_donors"],
                           old_odd_edited_rows_used_unmodified=frozen["old_odd_edited_rows_used_unmodified"],
                           even_eligible=scoring.evaluate(eligible,missing),
                           even_all_candidate_positive=scoring.evaluate(eligible+unchanged,opportunity["candidate_only"]),
                           historical_odd_eligible=old_score)
        pooled.extend(eligible)
        pooled_untouched.extend(unchanged)
        all_missing += opportunity["candidate_only"]
        eligible_missing += missing
    return dict(plan_sha256=plan_pin,odd_score_sha256=ODD_SCORE_PIN,cases=cases,
                pooled_even_eligible=scoring.evaluate(pooled,eligible_missing),
                pooled_even_all_candidate_positive=scoring.evaluate(pooled+pooled_untouched,all_missing))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot",type=Path)
    parser.add_argument("--score",nargs=2,metavar=("PLAN","SHA256"))
    args = parser.parse_args()
    sys.addaudithook(odd.deny_backing)
    if args.score:
        path,pin = args.score
        output = score(args.snapshot,odd.signed.document(Path(path),pin),pin)
    else:
        sys.addaudithook(odd.deny_installed_outcomes)
        output = predict(args.snapshot)
    print(json.dumps(output,sort_keys=True,separators=(",",":"),allow_nan=False))
