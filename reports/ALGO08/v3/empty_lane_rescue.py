"""Replay a causal retry schedule, then price and score it against separately opened full packets."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from .ds30_evidence_transfer import INSTALLED_0049, INSTALLED_0049_SHA, attempts, bind_publication, deny_backing, signed
from .ds30_oracle_routing import CAMPAIGN, PLAN, checked
from .full_successor_score import ARMS


CASES = ("DS30-0049", "DS30-0407")
GROUPS = ("neither", "peer", "previous", "both")


def schedule(opportunities):
    """Return one decision for each empty short lane using the current and previous visits only."""
    prior = {}
    decisions = {}
    rows = iter(opportunities.values())
    for left, right in zip(rows, rows, strict=True):
        pair = left, right
        stream = tuple(left["row"][key] for key in ("edge", "channel", "actual_rf_hz"))
        if ([row["radio"] for row in pair] != [0, 1] or left["short"] != right["short"]
                or left["counter"] != right["counter"] or stream != tuple(right["row"][key] for key in
                                                                           ("edge", "channel", "actual_rf_hz"))):
            raise ValueError("Expected original, aligned stereo opportunities")
        present = [row["factor"] is not None for row in pair]
        for radio, row in enumerate(pair):
            if row["short"] and not present[radio]:
                peer = present[1-radio]
                previous = prior.get((stream, radio), False)
                decisions[row["id"]] = GROUPS[int(peer) + 2 * int(previous)]
        prior.update({(stream, radio): value for radio, value in enumerate(present)})
    return decisions


def counts(decisions, targets):
    missed = set(targets)
    if not missed <= decisions.keys():
        raise ValueError("Reference targets must be short empty opportunities")
    empty = Counter(decisions.values())
    covered = Counter(decisions[key] for key in missed)
    selected = sum(empty.values()) - empty["neither"]
    hits = len(missed) - covered["neither"]
    return dict(empties=len(decisions), selected=selected, reference=len(missed), hits=hits,
                precision=hits/selected if selected else None, recall=hits/len(missed) if missed else None,
                cells={key: dict(empties=empty[key], reference=covered[key]) for key in GROUPS})


def inputs(case):
    plan = json.loads(checked(CAMPAIGN/"plan.json", PLAN))
    enrollment, = [row for row in plan["cases"] if row["case"] == case]
    folder = CAMPAIGN/"cases"/case
    pair_data = (folder/"pair.json").read_bytes()
    pair = json.loads(pair_data)
    if (pair["verified_pair"] is not True or pair["state"] != "observed_pair" or not pair["chronological"]
            or pair["actual_order"] != enrollment["order"]):
        raise ValueError("Original frozen pair has not verified")
    folders = attempts(folder, pair)
    candidate, pub, _ = bind_publication(folders["successor"], pair["attempt_result_sha256"]["successor"],
                                         "successor", pair)
    identity = candidate["raw_identity"]
    with (CAMPAIGN/"rows.jsonl").open() as source:
        row, = (r for line in source if (r := json.loads(line))["case"] == case and r["algorithm"] == "successor")
    if (any(row[key] != enrollment[key] for key in ("manifest_raw_authority_sha256", "raw_identity_sha256", "case_id"))
            or row["attempt_result_sha256"] != pair["attempt_result_sha256"]["successor"]
            or row["raw_authority_sha256"] != identity["raw_authority_sha256"] or not row["verified_pair"]
            or identity["window_count"] != enrollment["window_count"] or identity["recording"] != enrollment["recording"]):
        raise ValueError("Original accession differs from the candidate recording")
    witness_path = pub/"unified-short-bootstrap.json"
    witness = signed.document(witness_path)
    sparse, _, _ = signed.qualified_candidate(pub, witness, candidate["native_sha256"], identity["region_sha256"])
    opportunities = signed.opportunities(sparse)
    clock = witness["receiver_audit"]["native"]
    calls = Counter("short_primary" if row["short"] else "full" for row in opportunities.values())
    if (calls != clock["native_calls"] or not calls["full"] or
            witness["receiver_audit"]["recording_authority"] != identity["raw_authority_sha256"]):
        raise ValueError("Scheduled native work disagrees with the authenticated callback witness")
    receipt = dict(pair=signed.tag(pair_data), attempts=pair["attempt_result_sha256"], native=candidate["native_sha256"],
                   witness=signed.tag(witness_path.read_bytes()), decisions=schedule(opportunities))
    return receipt, pair, folders, candidate, sparse, opportunities, clock


def evaluate(case, frozen):
    fresh, pair, folders, candidate, sparse, right, clock = inputs(case)
    if fresh != frozen:
        raise ValueError("Candidate decisions or selected attempts changed since freezing")
    installed, pub, _ = bind_publication(folders["installed"], pair["attempt_result_sha256"]["installed"], "installed", pair)
    if installed["raw_identity"] != candidate["raw_identity"]:
        raise ValueError("Original identities differ")
    stock = signed.read_native(pub, installed["native_sha256"])
    if stock["provenance"]["detector_sha256"] != "sha256:" + signed.FULL:
        raise ValueError("Expected installed full-aperture detector")
    left = signed.opportunities(stock)
    signed.bind_pair(stock, sparse, left, right)
    decisions = frozen["decisions"]
    reference = {oid for oid in decisions if left[oid]["factor"] is not None}
    totals = counts(decisions, reference)
    owners = {}
    if case == "DS30-0049":
        trace = signed.document(INSTALLED_0049, INSTALLED_0049_SHA)
        if (trace["submitted_native_sha256"] != installed["native_sha256"] or
                trace["receipt"]["terminal_sha256"] != installed["evidence"]["receipt"]["terminal_sha256"]):
            raise ValueError("Installed owner witness differs")
        maps = signed.owners(trace["ordered_owners"], installed["evidence"]["owners"])
        for arm in ARMS:
            held = decisions.keys() & maps[arm].keys()
            if not held <= reference:
                raise ValueError("Installed owners require a positive on this opportunity")
            owners[arm] = counts(decisions, held)
    cost = {}
    for name, count in (("scheduled", totals["selected"]), ("every_empty", totals["empties"])):
        cost[name] = {metric: count * clock[f"native_{metric}_ns"]["full"] / clock["native_calls"]["full"] / 1e9
                      for metric in ("wall", "cpu")}
    return dict(installed_native=installed["native_sha256"], evidence=totals, installed_owners=owners,
                estimated_extra_callback_s=cost, observed_wall_s={role: row["elapsed_s"] for role, row in
                (("installed", installed), ("successor", candidate))}, native_calls=clock["native_calls"],
                full_callback_ns={m: clock[f"native_{m}_ns"]["full"] for m in ("wall", "cpu")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "score"))
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    sys.addaudithook(deny_backing)
    if args.action == "freeze":
        result = {case: inputs(case)[0] for case in CASES}
    else:
        if not args.frozen or not args.sha256:
            parser.error("Pass the frozen candidate decisions and their digest")
        frozen = json.loads(checked(args.frozen, args.sha256))
        if set(frozen) != set(CASES):
            raise ValueError("Unexpected enrollment")
        result = dict(frozen_sha256=args.sha256, cases={case: evaluate(case, frozen[case]) for case in CASES})
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
