"""Attribute the four sealed dense cold runs without launching inference."""

import argparse
from hashlib import sha256
import json
from math import dist
from pathlib import Path


ARCHIVES = {
    "full-mixed": (Path("/var/tmp/leo-v3-regional-dense-pair/native"), "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e"),
    "target": (Path("/dev/shm/leo-v3-modest-mask-results.0qfAjbDv/DS30-0008/target"), "22742b7b08a400f06df9263e8f3cfa8946bc20c9ff8fddeb9e9842625c60d7d2"),
    "causal": (Path("/dev/shm/leo-v3-causal-mask-dense-01/dense"), "8dded884cd12d52f95d135d4da850fbb5f7dc62ee1252d7553a7065170668f61"),
    "hindsight": (Path("/dev/shm/leo-v3-target-owner-recovery-01/dense"), "fb24dae00f05b586722997cb83f599f7bbde363873cde7813bd2de54d3f9c769"),
}
RACE_SHA = "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7"
ROOT = Path("/dev/shm/leo-v3-causal-cold-audit-results-02")
ABORTS = {
    "isolated_import": (ROOT.with_name("leo-v3-causal-cold-audit-results-01") / "process.json",
                        "5faf3ef8b6b17dec3ec7faf382732a39a3a36912a7a7e63da6429ca6d48ed046"),
    "installed_fallback_cancelled": (ROOT / "process.json", "d153e2cc7914e092a7450092129f3ae13b9b6601ef909fe6a958507adfb42664"),
}
ABORTED_TERMINAL = ROOT / "cold-only/fast-scan-automatic-work/algo08-v2-2a35248362339057a6a8486b1006c0e2/terminal.json"
ABORTED_TERMINAL_SHA = "393a9561bba14bca5a3a4008bbcecfe4d5f7239c8cdc09e8293036f55069da04"


def checked(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Sealed source changed: {path}")
    return json.loads(data)


def summarize(cold, clocks):
    prefix, completed = cold["prefix"], cold["completed"]
    if cold["routing"] not in ("winner_raced", "ambiguous_gap"):
        raise ValueError("Replay or unavailable finalist trace cannot use disjoint CPU accounting")
    if any(row["score"] is None for row in prefix) or len(prefix) != 3:
        raise ValueError("Expected three finite published prefixes")
    prefixes = {row["branch"]: row for row in prefix}
    finishes = {row["branch"]: row for row in completed}
    prefix_order = [r["branch"] for r in sorted(prefix, key=lambda r: (r["score"], r["branch"]))]
    final_order = [r["branch"] for r in sorted(completed, key=lambda r: (r["score"], r["branch"]))]
    if (final_order[0] != cold["branch"] or len(finishes) != (1 if cold["routing"] == "winner_raced" else 3)
            or any(prefixes[r["branch"]]["evaluations"] > r["first_evaluations"] for r in completed)):
        raise ValueError("Prefix, fit or winning decision contradict the archived race")
    prefix_s = sum(r["cpu_ns"] for r in prefix)/1e9
    suffix_s = sum(r["cpu_ns"] for r in completed)/1e9
    first = sum(finishes[b]["first_evaluations"] if b in finishes else p["evaluations"] for b,p in prefixes.items())
    second = sum(r["second_evaluations"] for r in completed)
    spread = max(r["score"] for r in completed) - min(r["score"] for r in completed) if len(finishes) > 1 else None
    return dict(clock=clocks, prefix_cpu_s=prefix_s, completion_cpu_s=suffix_s,
                setup_rank_and_other_cpu_s=clocks["cpu_s"]-prefix_s-suffix_s,
                first_objective_requests=first, refreshed_objective_requests=second, total_objective_requests=first+second,
                first_fits_completed=len(finishes), refreshed_fits_completed=len(finishes), prefix_order=prefix_order,
                final_order=final_order, final_score_spread=spread,
                prefix_score_spread=max(r["score"] for r in prefix)-min(r["score"] for r in prefix),
                winner_reversed=prefix_order[0] != final_order[0],
                final_penalty_for_selecting_prefix_leader=finishes[prefix_order[0]]["score"]-finishes[final_order[0]]["score"]
                    if prefix_order[0] in finishes else None,
                longest_first_phase=max(completed, key=lambda r: r["first_evaluations"])["branch"],
                cold=cold)


def owner_delta(full, compared):
    a, b = ({r[0]: r[1:] for r in rows} for rows in (full, compared))
    if len(a) != len(full) or len(b) != len(compared):
        raise ValueError("Unexpected duplicate owner row")
    shared = a.keys() & b.keys()
    return dict(total=len(b), shared=len(shared), lost=len(a)-len(shared), new=len(b)-len(shared),
                norad_changes=sum(a[k][0] != b[k][0] for k in shared), role_changes=sum(a[k][1] != b[k][1] for k in shared))


def archived():
    rows, full = {}, None
    for name, (directory, pin) in ARCHIVES.items():
        report = checked(directory / "joint-research-receipt.json", pin)
        if name == "full-mixed":
            full = report
        receipt, route = report["receipt"], report["route_details"]
        terminal_path = directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
        terminal = checked(terminal_path, receipt["terminal_sha256"])
        if (terminal["region"] != full["receipt"]["region"] or terminal["session_id"] != full["receipt"]["session_id"]
                or terminal["native_sha256"] != report["saved_digest"] or report["route"] != "complete"
                or report["source_sha256"]["cold_finalist_race.py"] != RACE_SHA):
            raise ValueError("Signed case, region, saved support or finalist implementation changed")
        region, = report["early_regional"]
        stats = summarize(route["cold"], route["cold_clocks"])
        stats.update(cold_rows=route["support"]["full_curved"], checked_region=region["result"],
                     cold_displacement_from_full_km=dist(route["cold"]["east_north_km"], full["route_details"]["cold"]["east_north_km"]),
                     owners_from_full={arm: owner_delta(full["selected_rows"][arm], owners)
                                       for arm, owners in report["selected_rows"].items()},
                     selected_roles=report["selected_roles"], terminal=terminal, terminal_sha256=receipt["terminal_sha256"],
                     report_sha256=pin, sources=report["source_sha256"], solve_cpu_s=report["solve"]["cpu_s"])
        rows[name] = stats
    return rows


def result():
    rows = archived()
    a, b = rows["target"], rows["causal"]
    lead = lambda r: next(q for q in r["cold"]["completed"] if q["branch"] == r["longest_first_phase"])
    aborted = checked(ABORTED_TERMINAL, ABORTED_TERMINAL_SHA)
    return dict(archived=rows, delta_target_to_causal=dict(
        **{k: b[k]-a[k] for k in ("prefix_cpu_s", "completion_cpu_s", "setup_rank_and_other_cpu_s", "total_objective_requests")},
        cold_cpu_s=b["clock"]["cpu_s"]-a["clock"]["cpu_s"],
        longest_completion_cpu_s=(lead(b)["cpu_ns"]-lead(a)["cpu_ns"])/1e9),
        failed_observer=dict(
            processes={name: checked(path, pin) for name,(path,pin) in ABORTS.items()},
            saved_fallback_terminal=dict(sha256=ABORTED_TERMINAL_SHA, decision=aborted["decision"], orbit_policy=aborted["orbit_policy"]),
            sampled_stack=["family_cavity.fit_cavity_proposals", "v5_core.infer", "blind_joint_route.route (installed fallback)"],
            instrumentation_failure_not_sealed=True, censored_fallback_excluded=True),
        waveform_calls=0, new_successful_numerical_audits=0, exact_duplicate_opportunity_measured=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    with options.output.open("x") as stream:
        json.dump(result(), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
