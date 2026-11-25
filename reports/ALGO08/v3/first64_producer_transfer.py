"""Reprice the frozen 64 DS30 field pairs from signed input-transport telemetry."""

import argparse
from gzip import compress, decompress
import json
from math import fsum, isclose
from pathlib import Path

from .ds30_oracle_routing import frozen_order
from .ds30_routing_first64 import BOUNDARY, EXPORT, LIMIT, SEAL, restricted_json, CASE_KEY
from .field_speed_reachability import BUILD, PLAN, STOCK, checked, digest, gates, reconcile
from .first24_slot_transfer import donors, transfer
from .grid_time_ceiling import MAP_TRIAL, MAP_PIN, grid_seconds
from .receiver_solver_targets import targets


NATURAL = "bb6942d2d7dc750ca51cbeeb7c5787427acd2df2f845641bf2ed8b456781536d"
NATURAL_JSON = "e58501f167a1d80e4a1267c769fde01f66857a0b01dfa9ba15da6fe9a492a3ce"
ROUTING = "6958f0a428eeb70ca147aa19c595a834298f1e613ae0776a07e448f230406b10"
ROSTER = "a29647c7b65701b2b67deab4203073122a1a8f5a7d9d1165cb5a133d39860796"
FROZEN_CLOCK = Path(__file__).parent / "measurements/ds30-routing-first64.json.gz"
NATIVE_RATE = 1.5


def select(snapshot, campaign):
    plan = json.loads(checked(campaign / "plan.json", PLAN))
    ordered = frozen_order(plan)
    roster = {row["case"]: row for row in ordered[:LIMIT]}
    if ordered[LIMIT]["case"] != BOUNDARY or digest(("\n".join(roster) + "\n").encode()) != ROSTER:
        raise ValueError("Expected the frozen pre-0218 order")
    seal = json.loads(checked(snapshot / "seal.json", SEAL))
    if seal["combined_sha256"] != EXPORT or seal["plan_sha256"] != "sha256:" + PLAN:
        raise ValueError("The field export must bind the exact plan")
    frozen = json.loads(decompress(checked(FROZEN_CLOCK, ROUTING)))
    archived = frozen["measurements"]
    if [row["case"] for row in archived] != list(roster):
        raise ValueError("The independent clock receipt differs from the preselected roster")
    export = checked(snapshot / "rows.jsonl", EXPORT)
    selected = {}
    for line in restricted_json(export.splitlines(), CASE_KEY, roster):
        row = json.loads(line)
        key = row["case"], row["algorithm"]
        entry = roster[key[0]]
        build = {"installed": STOCK, "successor": BUILD}[key[1]]
        if (key in selected or not row["verified_pair"] or not row["acquisition_verified"] or
            row["build_sha256"] != "sha256:" + build or row["actual_order"] != entry["order"] or
            row.get("relocation_proof_sha256") != seal["proofs"].get(key[0]) or
            any(row[field] != entry[field] for field in ("case_id", "raw_identity_sha256", "assigned_rank"))):
            raise ValueError("Unexpected field arm or authority in the frozen prefix")
        selected[key] = row, "sha256:" + digest(line)
    if len(selected) != 2 * LIMIT:
        raise ValueError("Every preselected original must have both measured arms")

    for case, frozen_row in zip(roster, archived, strict=True):
        (stock, a_pin), (candidate, b_pin) = (selected[case, role] for role in ("installed", "successor"))
        if (a_pin, b_pin) != tuple(frozen_row[role]["export_line_sha256"] for role in ("installed", "successor")):
            raise ValueError("The selected export row differs from the independent clock receipt")
        first, second = (selected[case, role][0] for role in stock["actual_order"])
        if first["child_finished_unix_ns"] > second["child_started_unix_ns"]:
            raise ValueError("The original timed arms were not in their signed order")
        detail = reconcile(campaign, stock, candidate)
        source = (campaign / candidate["attempt"]).parent / "publication/legacy-original-acquisition.json"
        ledger = json.loads(checked(source, detail["pins"]["legacy"]))
        work = detail["work"]
        grid = grid_seconds(ledger.get("acceleration", {}).get("solver", {}).get("grid"),
                            candidate["outcome"], work["solver"]["grid_cpu_s"])
        yield {k: detail[k] for k in ("case", "stock_wall_s", "actual_wall_s", "stock_cpu_s", "actual_cpu_s",
                                     "acquisition_s", "acquisition_cpu_s", "native_detector_s",
                                     "native_detector_process_cpu_s", "validator_s", "decision_publication_s", "pins")} | dict(
            grid=grid, solver=work["solver"]["wall_s"], stock_result=stock["attempt_result_sha256"],
            hits=work["prefetch"]["hits"], hit_bytes=work["prefetch"]["hit_bytes"],
            worker_cpu=work["prefetch"]["worker_cpu_ns"] / 1e9,
            demand_wait=work["prefetch"]["demand_wait_ns"] / 1e9, members=work["original_members"],
            input_bytes=work["original_encoded_bytes"])


def natural_donor(path):
    raw = decompress(checked(path, NATURAL))
    if digest(raw) != NATURAL_JSON:
        raise ValueError("Natural 0016 result differs between compressed and logical pins")
    receipt = json.loads(raw)
    runs = receipt["results"]["DS30-0016"]
    control, trial = (runs[name] for name in ("charted", "trial"))
    left, right = control["prefetch"], trial["prefetch"]
    member_keys = ("chunk_index", "first_sequence", "windows", "encoded", "decoded", "manifest_sha256",
                   "member_sha256", "index_sha256", "raw_sha256")
    controls, trials = ([[row[key] for key in member_keys] for row in run["verified_member_scopes"]]
                        for run in (control, trial))
    if (set(receipt["comparisons"]) != {"DS30-0016"} or control["outcome"] != "complete" or
        trial["outcome"] != "complete" or control["raw_identity"] != trial["raw_identity"] or
        control["native_sha256"] != trial["native_sha256"] or control["build"].removeprefix("sha256:") != BUILD or
        len(controls) != 13 or controls != trials or
        control["process"]["finished_unix_ns"] > trial["process"]["started_unix_ns"] or
        any(left[k] != right[k] for k in ("hit_bytes", "hits", "submitted_bytes", "submitted")) or
        left["hits"] != 11 or left["hit_bytes"] != 834_805_982 or left["fallback"] or right["fallback"]):
        raise ValueError("Expected the complete same-original combined trial with matched eligible input")
    observed = {}
    for key, run in (("charted", control), ("trial", trial)):
        acq = run["phases"]["authenticated_raw_acquisition"]
        proc = run["process"]
        verify = run["verification"]["wall_s"]
        paid = run["verified_boundary"]["wall_s"]
        worker = run["prefetch"]["worker_cpu_ns"] / 1e9
        native = fsum(run["receiver_audit"]["native"]["native_wall_ns"].values()) / 1e9
        if (not isclose(proc["elapsed_s"] + verify, paid, rel_tol=0, abs_tol=1e-9)
            or not 0 < worker <= acq["cpu_s"] or not 0 < native <= acq["elapsed_s"]):
            raise ValueError("Producer and verified time must nest within their measured boundaries")
        counts = run["numeric_process"]
        observed[key] = dict(producer_cpu=worker, acquisition_wall=acq["elapsed_s"], acquisition_cpu=acq["cpu_s"],
                             native_wall=native, acquisition_non_native_wall=acq["elapsed_s"] - native,
                             numeric_cpu=counts["cpu_s"], input_blocks=counts["input_blocks"],
                             major_faults=counts["major_faults"], paid_wall=paid, raw_wall=proc["elapsed_s"],
                             verifier_wall=verify, demand_wait=run["prefetch"]["demand_wait_ns"]/1e9)
    comparison = receipt["comparisons"]["DS30-0016"]["charted_trial"]
    return dict(hit_bytes=left["hit_bytes"], hit_count=left["hits"], observed=observed,
                scientific_grid=comparison["grid"],
                delta_seconds={name: observed["charted"][name]-observed["trial"][name]
                               for name in ("producer_cpu", "acquisition_wall", "acquisition_non_native_wall", "paid_wall")})


def prices(row, donor, unit):
    if unit not in {"bytes", "hits"}:
        raise ValueError("Credit only complete authenticated lookahead bytes or hits")
    eligible, reference = ((row["hit_bytes"], donor["hit_bytes"]) if unit == "bytes" else
                           (row["hits"], donor["hit_count"]))
    other = row["acquisition_s"] - row["native_detector_s"]
    producer = min(row["worker_cpu"], row["acquisition_cpu_s"] - row["native_detector_process_cpu_s"])
    deltas = donor["delta_seconds"]
    scopes = {"producer_cpu": (deltas["producer_cpu"], producer),
              "producer_cpu_if_wall": (deltas["producer_cpu"], min(other, producer)),
              "acquisition_wall": (deltas["acquisition_wall"], row["acquisition_s"])}
    if "acquisition_non_native_wall" in deltas:
        scopes["acquisition_non_native_wall"] = deltas["acquisition_non_native_wall"], other
    if "prefix_exit_wall" in deltas:
        predecision = row["actual_wall_s"] - row["decision_publication_s"] - row["validator_s"]
        scopes["prefix_exit_wall"] = deltas["prefix_exit_wall"], predecision
    if "paid_wall" in deltas:
        scopes["paid_wall"] = deltas["paid_wall"], row["actual_wall_s"]
    return {key: transfer(delta, eligible, reference, cap) for key, (delta, cap) in scopes.items()}


def assess(rows, credits, *, mode, native_rate=1., grid_fraction=1.):
    partitioned = {"none", "producer_cpu_if_wall", "acquisition_non_native_wall"}
    if mode not in partitioned and (native_rate != 1 or grid_fraction != 1):
        raise ValueError("Only explicitly disjoint wall shares can stack with receiver and solver changes")
    cpu = mode == "producer_cpu"
    data = [{"actual_wall_s": row["actual_cpu_s"], "stock_wall_s": row["stock_cpu_s"]}
            for row in rows] if cpu else rows
    native = [row["native_detector_s"] * (1 - 1 / native_rate) for row in rows]
    grid = [row["grid"] * (1 - grid_fraction) for row in rows]
    saving = [fsum(items) for items in zip(credits, native, grid, strict=True)]
    result = gates(data, saving)
    result.update(transferred=fsum(credits), summed_speedup=1/result["sum_ratio"],
                  median_paired_speedup=1/result["paired_median_ratio"],
                  both_gates=max(result["sum_ratio"], result["paired_median_ratio"]) <= .5)
    if mode in partitioned:
        residual = [row["actual_wall_s"] - saved for row, saved in zip(rows, saving, strict=True)]
        for label, pool in (("native", [row["native_detector_s"]-used for row, used in zip(rows, native, strict=True)]),
                            ("non_grid_solver", [row["solver"]-row["grid"] for row in rows])):
            value = targets([(row["stock_wall_s"], cost, 0., stage)
                             for row, cost, stage in zip(rows, residual, pool, strict=True)], 1.)
            result[f"additional_uniform_{label}_cut"] = value | dict(stage_s=fsum(pool))
    return result


def report(snapshot, campaign, measured):
    rows = list(select(snapshot, campaign))
    new = natural_donor(measured)
    history = donors()
    map_receipt = json.loads(checked(MAP_TRIAL, MAP_PIN))["new_cells"]
    if not all(entry["receipt"]["accept"] for entry in map_receipt.values()):
        raise ValueError("The previous standalone map controls are unavailable")
    ordinary, profiled = (map_receipt[k]["receipt"]["grid_audit"]["exact"]["elapsed_ns"]
                          for k in ("ordinary", "profiled"))
    fraction = profiled / ordinary
    configurations = dict(alone=(1., 1.), map_only=(1., fraction), native_and_map=(NATIVE_RATE, fraction))
    zeros = [0.] * LIMIT
    unchanged = {key: assess(rows, zeros, mode="none", native_rate=n, grid_fraction=g)
                 for key, (n, g) in configurations.items()}
    cases = {}
    for template, donor in {"0016_natural_combined": new, **history}.items():
        for unit in ("bytes", "hits"):
            priced = [prices(row, donor, unit) for row in rows]
            modes = set(priced[0])
            summary = {}
            for mode in sorted(modes):
                amounts = [r[mode] for r in priced]
                choices = configurations if mode in {"producer_cpu_if_wall", "acquisition_non_native_wall"} else {"alone": (1., 1.)}
                summary[mode] = {key: assess(rows, amounts, mode=mode, native_rate=n, grid_fraction=g)
                                 for key, (n, g) in choices.items()}
            cases[f"{template}_{unit}"] = dict(summary=summary, individual=priced)
    return dict(snapshot=dict(plan_sha256=PLAN, export_sha256=EXPORT, seal_sha256=SEAL, roster_sha256=ROSTER,
                              independent_clocks_sha256=ROUTING, excluded_from=BOUNDARY),
                donor=dict(seal=NATURAL, logical_sha256=NATURAL_JSON, trial=new, control=history),
                map_donor=dict(sha256=MAP_PIN, wall_fraction=fraction), source=digest(Path(__file__).read_bytes()),
                totals={key: sum(row[key] for row in rows) for key in (
                    "stock_wall_s", "actual_wall_s", "acquisition_s", "native_detector_s", "solver", "grid",
                    "hit_bytes", "hits", "input_bytes", "worker_cpu", "demand_wait")},
                baseline=unchanged, alternatives=cases, rows=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("snapshot", "campaign", "measured", "output"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    result = report(args.snapshot, args.campaign, args.measured)
    with args.output.open("xb") as output:
        output.write(compress(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))
