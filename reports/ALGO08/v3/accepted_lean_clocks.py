"""Read the accepted first-30 lean proposal clocks and exact reuse coverage."""

import argparse
from collections import Counter
import gzip
import json
from math import fsum, isclose
from pathlib import Path

from .field_fallback_budget import METRICS, clock
from .field_speed_reachability import BUILD, checked
from .first30_after_intake import EXPORT, HERE, PRE_EVIDENCE, remainder


FIRST30 = "5d7b3624bca9f1d808cb0bee044fcadb7c4593054da771d8c57dc0dd1456de3c"
SOURCES = (
    "blind_joint_finish.py", "blind_joint_route.py", "certified_salvage.py",
    "cold_finalist_race.py", "combined_successor.py", "combined_successor_raw_entry.py",
    "history_risk_route.py", "isolated_salvage.py", "joint_publication.py", "lighter_joint_estimator.py",
    "nomination_handoff.py",
)


def partition(attempt, risk):
    trial = attempt["provisional_salvage"]
    if trial["status"] not in ("untouched", "reverted") or "predictive_and_pair_clocks" in trial:
        raise ValueError("An executed provisional pair needs a separate nesting reconciliation")
    cold = attempt["cold"]
    rank = risk["two_centre_rank"]
    conf = attempt["sensitive_confidence"]
    recorded = {n: clock(attempt[f"{n}_clocks"]) for n in PRE_EVIDENCE if f"{n}_clocks" in attempt}
    stages = {metric: {n: recorded.get(n, {}).get(metric, 0.) for n in PRE_EVIDENCE}
              for metric in METRICS}
    children = {}
    totals = clock(attempt["candidate_pre_evidence_clocks"])
    for metric, parts in stages.items():
        parts.update(second_seed_gate=clock(trial["seed_gate_clocks"])[metric],
                     isolated_admission_and_fit=clock(trial["isolation_clocks"])[metric])
        parts["other"] = remainder(totals[metric], *parts.values())
        key = metric.removesuffix("_s") + "_ns"
        nested = dict(
            rank_scout=rank["paid"][key]/1e9,
            rank_retry=rank.get("ordinary_retry", {}).get(key, 0)/1e9,
        )
        if metric == "cpu_s":
            for name in ("prefix", "completed"):
                nested["finalist_"+name] = fsum(x["cpu_ns"] for x in cold[name])/1e9
        nested["other"] = remainder(parts["cold"], *nested.values())
        children[metric] = dict(cold=nested,
                                sensitive_confidence=fsum(x["clocks"][metric] for x in conf))
    return stages, children


def read_case(row, candidate, campaign, sources):
    path = (campaign / candidate["attempt"]).resolve(strict=True)
    if not path.is_relative_to(campaign):
        raise ValueError("Expected an original saved result under the local campaign")
    result = json.loads(checked(path, row["pins"]["result"]))
    witness = json.loads(checked(path.parent / "publication/exact-named-raw-witness.json",
                                 row["pins"]["scientific"]))
    detail = witness["evidence"]["detail"]
    risk = witness["ports"]["history_risk"]
    attempt, = risk["lean_attempts"]
    if (candidate["attempt_result_sha256"] != row["pins"]["result"]
            or candidate["build_sha256"] != f"sha256:{BUILD}"
            or not candidate["verified_pair"] or not candidate["acquisition_verified"]
            or result["native_sha256"] != row["pins"]["native"]
            or detail["input_sha256"] != row["pins"]["native"]
            or detail["terminal_sha256"] != candidate["terminal_sha256"]
            or risk["choice"]["route"] != "lean" or attempt["decision"] != "complete"
            or any(sources[name] != pin for name, pin in witness["source_sha256"].items() if name in sources)):
        raise ValueError("Accepted witness differs from the authenticated field result")
    parts, nested = partition(attempt, risk)
    for metric in METRICS:
        if not isclose(fsum(parts[metric].values()),
                       row["phases"]["solver"][metric]["accepted_proposal"], rel_tol=0., abs_tol=1e-6):
            raise ValueError("Accepted proposal clocks disagree with the original panel")
    support = attempt["support"]
    both = not support["cold_rejected_tracks"] and "salvage" not in support
    eligible = both and support["initial_curved"] == support["full_curved"] > 0
    if eligible and (support["rechecked_curved"] != support["initial_curved"]
                     or support["second_curved_rejections"]):
        raise ValueError("A second screen changed the source-certified full support")
    salvage = attempt["certified_salvage"]
    profiles = salvage.get("profile_calls", 0)
    distinct_max = sum(track["supports_tested"] for track in support.get("salvage", ()))
    return dict(case=row["case"], pins=row["pins"], stages=parts, nested=nested,
                cold_route=attempt["cold"]["routing"],
                trial=attempt["provisional_salvage"]["status"],
                seed_reuse=eligible,
                support={k: support.get(k) for k in ("full_curved", "initial_curved", "curved_restored",
                                                     "rechecked_curved")},
                whitening=dict(profiles=profiles, distinct_supports_upper=distinct_max,
                               duplicate_matrices_lower=max(0, profiles-distinct_max),
                               whole_exact_fine_cpu_upper=salvage.get("fine_exact_cpu_s", 0.0)))


def summarize(cases):
    totals = {}
    for metric in METRICS:
        stages = {k: fsum(r["stages"][metric][k] for r in cases) for k in cases[0]["stages"][metric]}
        cold = {k: fsum(r["nested"][metric]["cold"][k] for r in cases)
                for k in cases[0]["nested"][metric]["cold"]}
        if not isclose(stages["cold"], fsum(cold.values()), abs_tol=1e-6):
            raise ValueError("Cold children do not reconcile")
        totals[metric] = dict(
            stages=stages, cold=cold,
            sensitive_confidence=fsum(r["nested"][metric]["sensitive_confidence"] for r in cases),
            whole_duplicate_seed_gate_upper=fsum(r["stages"][metric]["second_seed_gate"]
                                                  for r in cases if r["seed_reuse"]),
        )
    return dict(clocks=totals, cold_routes=dict(Counter(r["cold_route"] for r in cases)),
                trials=dict(Counter(r["trial"] for r in cases)),
                whitening={k: fsum(r["whitening"][k] for r in cases) for k in cases[0]["whitening"]})


def run(snapshot, campaign, build_file, charted_source):
    original = json.loads(gzip.decompress(checked(HERE / "first30-after-intake.json.gz", FIRST30)))
    build = json.loads(checked(build_file, BUILD))
    sources = {f"reports/ALGO08/v3/{name}": build["sources"][f"reports/ALGO08/v3/{name}"] for name in SOURCES}
    for name, pin in sources.items():
        checked(charted_source / name, pin)
    candidates = {}
    for line in checked(snapshot / "rows-with-relocations.jsonl", EXPORT).splitlines():
        row = json.loads(line)
        if row["algorithm"] == "successor":
            candidates[row["case"]] = row
    accepted = [r for r in original["cases"] if r["phases"]["solver"]["elapsed_s"]["accepted_proposal"] > 0]
    if len(original["cases"]) != 30 or len(accepted) != 25:
        raise ValueError("Expected 25 accepted lean proposals in the sealed first 30 pairs")
    cases = [read_case(r, candidates[r["case"]], campaign.resolve(), sources) for r in accepted]
    return dict(pins=dict(first30=FIRST30, export=EXPORT, build=BUILD, charted_commit=build["charted_commit"],
                          sources=sources),
                summary=summarize(cases), cases=cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "campaign", "build_file", "charted_source"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.snapshot, args.campaign, args.build_file, args.charted_source),
                     indent=2, sort_keys=True))
