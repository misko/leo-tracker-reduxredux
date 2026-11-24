"""Bound a same-input receiver acceleration from the first 30 original field receipts."""

import argparse
from collections import Counter
import gzip
from math import fsum, isclose
import os
from pathlib import Path
from statistics import median
import sys
import json

from .ds30_centered_error import selected_rows, verified_capture, verified_overlay
from .ds30_oracle_routing import CAMPAIGN, PLAN, checked, frozen_order
from .full_successor_score import MANIFEST, roster


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXPORT = "sha256:2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
SEAL = "sha256:84fc1193f55485f66a20b703fc52540fb8c94301937769759e4ed07a75b3af92"
STOCK = Path("/opt/leo-algo08/algo08v3")
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
DETECTOR = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SOURCE = {
    STOCK/"run": "sha256:fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448",
    STOCK/"payload/tools/algo08_scan.py": "sha256:573d6608597f1619785688769e7504a4ad8ac30dd71fecd37876c678ed4aca53",
    RELEASE/"src/leo/storage/fast_scan.py": "sha256:db79b4e50c10a3b948c69c86a464fb57a226b0dbb2955cf90d8ae83db3f39527",
}
DATASET = ROOT/"reports/2026_11_20_ds30_fast/dataset/manifest.json.gz"
DONOR = HERE/"measurements/installed-receiver-control-0016.json.gz"
DONOR_PIN = "sha256:e825bc3bc7bed415a21a65b35a0b7b75e12e65f57dde32864bdae829234c193d"
NORMAL_SCOPE = "raw_launcher_through_exit_plus_common_publication_verification"
FAILURE_SCOPE = "raw_launch_to_exit"
SLACK = .010


def no_backing(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
                or path.suffix in {".tle", ".png"} or path.name.endswith((".tle.gz", ".ci16.zst"))):
            raise ValueError("Benchmark receipt audit cannot open waveforms, orbit bodies or PNGs")


def clock_spans(result, native_ns, inventory_ns, terminal_ns):
    """Return disjoint elapsed spans and a single-CPU bound, with original timing scope."""
    child, validate = (result[k] for k in ("process", "validation"))
    start, end = (child[k] for k in ("started_unix_ns", "finished_unix_ns"))
    wall, cpu = child["elapsed_s"], child["cpu_s"]
    cancelled = result["outcome"] == "solver_failed"
    elapsed_verifier, cpu_verifier = (0., 0.) if cancelled else (validate["elapsed_s"], validate["cpu_s"])
    if (result["timing_scope"] != (FAILURE_SCOPE if cancelled else NORMAL_SCOPE)
            or bool(child["exit_code"]) != cancelled or child["timed_out"]
            or abs((end-start)/1e9-wall) > SLACK or not 0 <= cpu <= wall+SLACK
            or not isclose(result["elapsed_s"], wall+elapsed_verifier, abs_tol=1e-6, rel_tol=0.)
            or not isclose(result["cpu_s"], cpu+cpu_verifier, abs_tol=1e-6, rel_tol=0.)):
        raise ValueError("Published stopwatch differs from the retained one-core child and verifier")
    if ((terminal_ns is None) != cancelled or not start <= native_ns <= inventory_ns <= (terminal_ns or end) <= end):
        raise ValueError("Retained file timestamps cannot partition the original elapsed scope")
    prefix = (native_ns-start)/1e9
    inventory = (inventory_ns-start)/1e9
    terminal = (terminal_ns-start)/1e9 if terminal_ns is not None else wall
    if not 0 < prefix <= inventory <= terminal <= wall:
        raise ValueError("Retained timestamps disagree with the child stopwatch")
    if terminal_ns is not None and abs(terminal-result["evidence"]["terminal_file_s"]) > SLACK:
        raise ValueError("The elapsed terminal timestamp differs from the original sealed verification")
    after_native = wall-prefix
    cap = dict(lower=max(0., cpu-after_native-SLACK), upper=min(cpu, prefix+SLACK))
    if cap["lower"] > cap["upper"]:
        raise ValueError("One processor could not have supplied the child CPU in the measured spans")
    return dict(through_native_write=prefix, native_to_inventory_write=inventory-prefix,
                inventory_to_terminal_write=terminal-inventory if terminal_ns is not None else 0.,
                inventory_to_failed_exit=terminal-inventory if terminal_ns is None else 0.,
                terminal_to_exit=wall-terminal, verifier=elapsed_verifier,
                actual_failure_diagnostic_not_in_scope=validate if cancelled else None,
                verifier_cpu=cpu_verifier, child_cpu=cpu, child_wall=wall, prefix_cpu_bound=cap,
                unused_cpu_capacity=wall-cpu)


def ratios(baseline, durations):
    return dict(paired_median=median(y/x for x,y in zip(baseline,durations,strict=True)),
                summed=fsum(durations)/fsum(baseline), total=fsum(durations))


def scale_threshold(baseline, fixed, work):
    """Uniform units of work per second for both gates, or no finite value."""
    best = ratios(baseline, fixed)
    result = dict(free=best, required_rate=None, achieved=None, individual_free_passes=sum(
        y<=x/2 for x,y in zip(baseline,fixed,strict=True)))
    if max(best["paired_median"], best["summed"]) >= .5:
        return result

    def at(rate):
        return ratios(baseline, [keep+cost/rate for keep,cost in zip(fixed,work,strict=True)])

    for gate in ("paired_median", "summed"):
        lo, hi = 0., 1.
        while at(hi)[gate] > .5:
            hi *= 2
        for _ in range(66):
            mid = (lo+hi)/2
            if at(mid)[gate] > .5:
                lo = mid
            else:
                hi = mid
        result[gate+"_required_rate"] = hi
    result["required_rate"] = max(result[gate+"_required_rate"] for gate in ("paired_median", "summed"))
    result["achieved"] = at(result["required_rate"])
    return result


def one(path, pattern):
    (result,) = path.glob(pattern)
    if result.is_symlink() or not result.is_file():
        raise ValueError("Expected an immutable retained publication file")
    return result


def study_case(campaign, row, attempt, bytes_signed, expected_spec):
    path = campaign/row["attempt"]
    publication = path.parent/"publication"
    identity = attempt["raw_identity"]
    receipt = attempt["evidence"]["receipt"]
    case = row["case"]
    native_path = one(publication, "fast-scan-automatic-work/*/detections.json")
    native = json.loads(checked(native_path, attempt["native_sha256"]))
    source = native["source"]
    original = dict(raw_recording_authority_digest=identity["raw_authority_sha256"],
                    input_manifest_sha256=identity["inventory_sha256"], session_id=identity["session_id"])
    if (any(source[key] != value for key,value in original.items())
            or native["provenance"]["detector_sha256"] != DETECTOR
            or len(source["probes"]) != 2*receipt["counts"]["processed"]
            or native["clock_anchor"]["before"]["realtime_ns"] != identity["causal_cutoff_utc_ns"]):
        raise ValueError(f"Installed receiver packet lacks original detector/authority binding for {case}")
    inventory = one(publication, "fast-scan-inputs/*.json")
    checked(inventory, identity["inventory_sha256"])
    command = json.loads((path.parent/"launch.json").read_bytes())["command"]
    if command[0] != str(STOCK/"run") or set(command[1::2]) != {"--recording", "--archive", "--region", "--bulk-root"}:
        raise ValueError(f"Installed original run used unexpected options for {case}")
    if attempt["outcome"] != "solver_failed":
        release = json.loads((publication/"algo08v3-release.json").read_bytes())
        if (release["frozen_specification"] != expected_spec or "sha256:"+release["detector_sha256"] != DETECTOR
                or release["decision"] != receipt["decision"] or release["session_id"] != identity["session_id"]):
            raise ValueError("Retained installed release marker changed")
        path_t = publication/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json"
        terminal = json.loads(checked(path_t, receipt["terminal_sha256"]))
        if (terminal["native_sha256"] != attempt["native_sha256"]
                or terminal["arms"] != attempt["evidence"]["arms"]):
            raise ValueError("Installed published terminal changed")
        terminal_ns = path_t.stat().st_mtime_ns
    else:
        if list(publication.glob("fast-scan-automatic-work/*/terminal.json")) or not attempt["reached_solver"]:
            raise ValueError("Failure does not establish the recorded saved native boundary")
        terminal_ns = None
    stamps = dict(native=native_path.stat().st_mtime_ns, inventory=inventory.stat().st_mtime_ns, terminal=terminal_ns)
    return dict(case=case, outcome=attempt["outcome"], raw=identity["raw_authority_sha256"],
                result=row["attempt_result_sha256"], native=attempt["native_sha256"],
                wall=attempt["elapsed_s"], cpu=attempt["cpu_s"], lanes=len(source["probes"]),
                compressed_bytes=bytes_signed, timestamps=stamps, original_clock=attempt["process"],
                lookahead_advice=receipt.get("member_lookahead"), phases=clock_spans(attempt,*stamps.values()))


def population(cases):
    wall = [x["wall"] for x in cases]
    cpu = [x["cpu"] for x in cases]
    prefix = [x["phases"]["through_native_write"] for x in cases]
    fixed = [w-a for w,a in zip(wall,prefix,strict=True)]
    out = dict(cases=len(cases), wall=fsum(wall), cpu=fsum(cpu),
               prefix_speedup=scale_threshold(wall,fixed,prefix),
               twice_as_fast_prefix=ratios(wall, [r+a/2 for r,a in zip(fixed,prefix,strict=True)]),
               effective_MB_s=scale_threshold(wall, fixed,[x["compressed_bytes"]/1e6 for x in cases]),
               wall_half_budget_remaining_after_native=fsum(wall)/2-fsum(fixed),
               actual_prefix_MB_s=fsum(x["compressed_bytes"]/1e6 for x in cases)/fsum(prefix),
               lanes=sum(x["lanes"] for x in cases), bytes=sum(x["compressed_bytes"] for x in cases))
    out["CPU_prefix_bounds"] = {}
    out["wall_keeping_original_off_CPU_bounds"] = {}
    for edge in ("lower", "upper"):
        opportunity = [x["phases"]["prefix_cpu_bound"][edge] for x in cases]
        out["CPU_prefix_bounds"][edge] = scale_threshold(cpu,[c-a for c,a in zip(cpu,opportunity,strict=True)],opportunity)
        out["wall_keeping_original_off_CPU_bounds"][edge] = scale_threshold(
            wall,[w-a for w,a in zip(wall,opportunity,strict=True)],opportunity)
    out["wall_spans_s"] = {key: fsum(row["phases"][key] for row in cases) for key in (
        "through_native_write", "native_to_inventory_write", "inventory_to_terminal_write", "inventory_to_failed_exit",
        "terminal_to_exit", "verifier")}
    out["observed_lookahead_advice_cpu_s"] = fsum(x["lookahead_advice"]["cpu_ns"]/1e9 for x in cases if x["lookahead_advice"])
    out["observed_lookahead_advice_cases"] = sum(x["lookahead_advice"] is not None for x in cases)
    return out


def outside_panel_donor(cases):
    donor = json.loads(gzip.decompress(checked(DONOR, DONOR_PIN)))
    timing = donor["candidate"]["phases"]["authenticated_raw_acquisition"]
    work = donor["native_work"]
    calls = work["native_calls"]["full"]
    native_cpu = work["native_cpu_ns"]["full"]/1e9
    if (not donor["qualified"] or not donor["science_exact"] or "DS30-0016" in {x["case"] for x in cases}
            or donor["candidate"]["native_sha256"] != donor["stock_archival"]["native_sha256"]):
        raise ValueError("The outside-panel clock does not bind a same-detector control")
    rate = native_cpu/calls
    # This is a sensitivity, not a timer from the observed field cohort.
    modeled = [min(x["phases"]["prefix_cpu_bound"]["upper"], x["lanes"]*rate) for x in cases]
    return dict(case="DS30-0016", receipt=DONOR_PIN, independently_measured_full_receiver_acquisition=timing,
                native_cpu_s=native_cpu, native_lane_calls=calls, cpu_s_per_lane=rate,
                hypothetical_field_free_native_cpu_work_s=fsum(modeled),
                hypothetical_field_free_native_under_donor_rate={metric:ratios(
                    [x[metric] for x in cases], [x[metric]-credit for x,credit in zip(cases,modeled,strict=True)])
                    for metric in ("wall", "cpu")})


def study(snapshot, campaign=CAMPAIGN):
    plan = json.loads(checked(snapshot/"plan.json", PLAN))
    seal = json.loads(checked(snapshot/"rows-with-relocations-seal.json", SEAL))
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT or plan["cpu"] != 2:
        raise ValueError("Snapshot and installed one-core scope changed")
    for path, pin in SOURCE.items():
        checked(path, pin)
    order = frozen_order(plan)[:30]
    labels = tuple(row["case"] for row in order)
    rows = selected_rows(checked(snapshot/"rows-with-relocations.jsonl", EXPORT), labels)
    overlay = verified_overlay(campaign, seal)
    members = {m["dataset_label"]: m for m in json.loads(checked_dataset())["members"]}
    enrollment = roster()
    output = []
    for row in order:
        case = row["case"]
        _, pins = verified_capture(campaign,row,rows[case],enrollment[case],overlay)
        installed = rows[case]["installed"]
        attempt = json.loads(checked(campaign/installed["attempt"], pins["attempts"]["installed"]))
        source = members[case]
        if source["raw_authority_digest"] != row["manifest_raw_authority_sha256"]:
            raise ValueError("Logical source sizes lost original manifest authority")
        bytes_signed = sum(c["compressed_bytes"] for c in source["raw_recording"]["chunks"])
        result = study_case(campaign, installed, attempt, bytes_signed, plan["stock"]["frozen_specification"])
        result["pair"] = pins["pair_sha256"]
        output.append(result)
    summary = population(output)
    observed = {metric:ratios([m[metric] for m in output],[rows[case]["successor"][key] for case in labels])
                for metric,key in (("wall","elapsed_s"),("cpu","cpu_s"))}
    cohorts = {outcome:population([r for r in output if r["outcome"]==outcome])
               for outcome in ("complete", "withheld", "solver_failed")}
    return dict(scope=labels, sources={str(k):v for k,v in SOURCE.items()}, combined_export=EXPORT, seal=SEAL,
                original_order=PLAN, outcomes=Counter(x["outcome"] for x in output), cases=output,
                terminal_timestamp_coverage=sum(r["timestamps"]["terminal"] is not None for r in output),
                native_and_inventory_timestamp_coverage=len(output), direct_installed_acquisition_coverage=0,
                observed_successor=observed, aggregate=summary, by_outcome=cohorts, outside_panel_donor=outside_panel_donor(output),
                minimum_average_cpu_saving_per_lane_at_summed_wall_gate=summary["wall"]/2/summary["lanes"],
                waveform_reads=0, tle_reads=0, png_reads=0)


def checked_dataset():
    from .full_successor_score import checked as checked_bytes

    return checked_bytes(gzip.decompress(DATASET.read_bytes()), MANIFEST)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.addaudithook(no_backing)
    result = study(args.snapshot)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
