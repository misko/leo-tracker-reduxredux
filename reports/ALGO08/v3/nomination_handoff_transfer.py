"""Check the handoff's producer and consumer against archived DS30 chronology."""

import argparse
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
BASE = "2b98421e9a2192f29692e88446e580233ad83bd5"
PINS = {
    "history-risk-0004.json.gz": "e3fb84cfdd701d9edc5d8e912ad62c71065ae56261be3d7e10482f524bb99066",
    "nomination-handoff-0004-publication.json": "a32995249cd1b03f1c0383eb754f712ea5d997e041c62feed7f99a1e64715a6b",
    "history-risk-six-case.json.gz": "56526836f300cc9085c4a6b82ebb69c1beb13758444c4e54683d63d12b68a612",
    "history-risk-dense-mixed.json.gz": "f5402ce55606fc16ddbdf2bbb5ad40a7e1710b9db1bcb3b971556fff9cd246b4",
    "catalogue-block-bound.json.gz": "9d0503710be7a4dbbe1b355d25f9085718a8d5fc9248c313a4314b17cf20f1ff",
    "catalogue-block-dense-pair.json.gz": "221619809450842843221dcd6dc4b80412d19fd5a661318c447b738bd6c3bf68",
    "endpoint-track-repair-0160.json.gz": "4acbceb8b923b899ce967eac0304c697f9b1954f74959f8b3a3a512a0a326018",
}
SOURCE_PINS = {
    "nomination_handoff.py": "28de1e1061c174d8d83ada8441ae0ee242e22e9c5113c07f48371e26142636ef",
    "cold_finalist_race.py": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
}
STAGES = {case: f"leo-v3-history-risk-{case}-01" for case in ("0160", "0169", "0316", "0374", "0402")}
STAGES["0138"] = "leo-v3-history-risk-0138-pair02"


def checked(body, expected):
    if sha256(body).hexdigest() != expected:
        raise ValueError("Archived provenance digest changed")
    return body


def git_body(path, pin):
    return checked(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{BASE}:reports/ALGO08/v3/{path}"]), pin)


def load_stage(path, pin):
    if path.resolve(strict=True) != path or path.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("Expected only direct already staged tmpfs receipts")
    return json.loads(checked(path.read_bytes(), pin))


def chronology(choice, attempts):
    """Replay admission facts available in the saved cold and terminal chronology."""
    if choice == "named":
        if attempts:
            raise ValueError("Named dispatch must bypass the lean producer")
        return dict(route="direct_named", producer_entered=False, named_fallback_consumer=False,
                    completed_prefixes=0, handoff_on_archived_trace=False)
    (attempt,) = attempts
    cold = attempt["cold"]
    scores, outcomes = cold["scores"], cold["completed"]
    complete = sorted(row["branch"] for row in outcomes if row["score"] is not None and isfinite(row["score"]))
    if (not scores or len(scores) > 3 or complete != [i+1 for i,s in enumerate(scores) if s is not None]
            or any(r["score"] != scores[r["branch"]-1] for r in outcomes)):
        raise ValueError("Archived finalists disagree with their ordered scores")
    numeric_checkpoint_shape = len(complete) == len(scores) and all(
        len(row["point"]) == 2 and all(map(isfinite, row["point"]))
        and len(row["labels"]) == len(row["posterior"])
        and row["labels"] == sorted(set(row["labels"])) and all(map(isfinite, row["posterior"]))
        for row in outcomes
    )
    fallback = attempt["decision"] == "fallback"
    if not fallback:
        fires = False
    elif not numeric_checkpoint_shape:
        fires = False
    else:
        # Report structural eligibility without claiming the live identity/array guard passed.
        fires = None
    return dict(route=attempt["decision"], reason=attempt.get("reason"), producer_entered=True,
                named_fallback_consumer=fallback, routing=cold["routing"], nominated=len(scores),
                first_refresh_pauses=len(cold["prefix"]), completed_prefixes=len(complete),
                numeric_checkpoint_shape=numeric_checkpoint_shape, ordered_c0_scores=scores,
                winner=cold["branch"], cold_cpu_s=attempt["cold_clocks"]["cpu_s"],
                fallback_cpu_s=attempt.get("fallback_clocks", {}).get("cpu_s"),
                handoff_on_archived_trace=fires)


def rank_component(paired, nodes):
    if (not paired["cold_nodes_byte_equal"] or not paired["ordered_signatures_match"]
            or paired["candidate_digest"] != paired["control_digest"] or nodes < 3):
        raise ValueError("Rank-only clock requires the complete matching original nodes")
    a, b = (paired[port]["cpu_ns"] for port in ("control", "candidate"))
    return dict(nodes=nodes, nodes_sha256=paired["candidate_digest"], original_rank_cpu_ns=a,
                grouped_rank_cpu_ns=b, grouped_rank_only_cpu_ns_saved=a-b)


def audit(documents, stage_root):
    enrolled = documents["history-risk-six-case.json.gz"]["enrolled"]
    identified = {}
    for case, row in enrolled.items():
        result = row["result"]
        name = "routed/risk-route.json" if case == "0138" else "risk-route.json"
        stage = stage_root / STAGES[case]
        (trace,) = load_stage(stage/name, result["binds"][name])["solves"]
        choice = trace["choice"]["route"]
        if (choice != result["route"]["route"] or trace["choice"]["reason"] != result["route"]["reason"]
                or row["source_stage"]["sources"]["cold_finalist_race.py"] != SOURCE_PINS["cold_finalist_race.py"]):
            raise ValueError("Saved route and committed terminal digest frame disagree")
        identified["DS30-"+case] = chronology(choice, trace["lean_attempts"]) | {
            "signed_trace_sha256": result["binds"][name], "dispatch_reason": trace["choice"]["reason"],
            "elapsed_s": result["clock"]["elapsed_s"],
        }

    medium = documents["catalogue-block-bound.json.gz"]["medium_pair"]
    medium_meta = enrolled["0316"]["result"]
    work = medium["binding"]["request"]
    medium_stage = stage_root / STAGES["0316"]
    binding = load_stage(medium_stage/"binding.json", medium_meta["binds"]["binding.json"])["input"]
    request = Path(binding["request"])
    stage_request = stage_root / request.parent.name / request.name
    matched = load_stage(stage_request, binding["packets"][str(request)])
    keys = ("native_sha256", "inventory", "original_archive", "offer_sha256", "causal_cutoff_utc_ns", "raw_authority")
    if any(work[key] != matched[key] for key in keys):
        raise ValueError("Grouped-rank component scope belongs to a different saved request")
    rank = medium["result"]["rank"]
    identified["DS30-0316"]["matched_rank_component"] = rank_component(rank["paired"], rank["ordered_ranks"])
    identified["DS30-0316"]["native_sha256"] = matched["native_sha256"]

    dense = documents["history-risk-dense-mixed.json.gz"]
    dense_trace = dense["routed"]["ports"]["history_risk"]
    dense_req = dense["binding"]["request"]
    dense_rank = documents["catalogue-block-dense-pair.json.gz"]
    rank_req = dense_rank["binding"]["request"]
    matching = {"native_file": "packet", "inventory": "inventory", "offer_sha256": "offer_sha256",
                "raw_authority": "authority", "causal_cutoff_utc_ns": "cutoff_utc_ns", "local_archive": "archive"}
    if any(rank_req[key] != dense_req[field] for key,field in matching.items()):
        raise ValueError("Dense rank and signed accepting route do not bind the same staged input")
    rank = dense_rank["result"]["rank"]
    identified["DS30-0008"] = chronology(dense_trace["choice"]["route"], dense_trace["lean_attempts"]) | {
        "matched_rank_component": rank_component(rank["paired"], rank["ordered_ranks"]), "native_sha256": dense_req["native"],
    }

    old = documents["endpoint-track-repair-0160.json.gz"]["results"]["control"]
    forced = chronology("lean", old["recovered_inference"]["attempts"])
    if old["terminal"]["native_sha256"] != enrolled["0160"]["result"]["published"]["terminal"]["native_sha256"]:
        raise ValueError("Historical forced-lean control is a different native packet")
    historical = documents["history-risk-0004.json.gz"]["receipt"]["routed/risk-route.json"]["solves"][0]
    account = chronology(historical["choice"]["route"], historical["lean_attempts"])
    proof = documents["nomination-handoff-0004-publication.json"]
    observed = proof["handoff"]
    if (not proof["scientific_exact"] or observed["prefixes_reused"] != account["nominated"]
            or observed["rank_reuses"] != 1 or observed["scan_reuses"] != 1):
        raise ValueError("0004's live validation no longer binds the claimed handoff")
    return dict(schema="nomination-handoff-transfer-audit-v1", snapshot=BASE, source_pins=SOURCE_PINS, receipt_pins=PINS,
                primary_accepting_case="DS30-0316", by_case=identified,
                historical_forced_lean_0160=forced, measured_0004=account | {"live_handoff": observed},
                inventory_scope="named six-case saved publications plus separate full mixed DS30-0008",
                additional_current_natural_fallbacks=sum(row["named_fallback_consumer"] for row in identified.values()),
                new_solver_runs=0, waveform_reads=0, backing_archive_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stage-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    for path, pin in SOURCE_PINS.items():
        git_body(path, pin)
    documents = {}
    for filename, pin in PINS.items():
        body = git_body("measurements/" + filename, pin)
        documents[filename] = json.loads(gzip.decompress(body) if filename.endswith(".gz") else body)
    values = audit(documents, args.stage_root)
    with args.output.open("x") as stream:
        json.dump(values, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
