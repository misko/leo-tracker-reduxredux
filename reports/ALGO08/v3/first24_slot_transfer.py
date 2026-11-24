"""Price the signed, stage-bounded slot donor sensitivities on the fixed DS30 prefix."""

import argparse
import gzip
import json
from hashlib import sha256
from math import fsum, isfinite
from pathlib import Path

from .ds30_oracle_routing import frozen_order
from .field_fallback_budget import FIRST, FIRST_SEAL
from .field_speed_reachability import BUILD, PLAN, STOCK, checked, gates, reconcile

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"
DONOR_0016 = "d6423cc7aed51bb40f6c1b42836bd629a92847526ca084f409fa35e61dd65e5a"
DONOR_0049 = "c50cbd0327d7847fbced29e76c7b12605b18693315ca66cb0764faff0f90ba88"
FALLBACK_PIN = "3e96e728f74b7d977cc20b8b1bf08a8c44506c0d55f301c706ef1f2fbd8989db"
TREATMENTS = {
    "keep_measured_calls": (),
    "skip_rejected_proposal": ("rejected",),
    "free_named_fallback": ("fallback",),
    "both_free": ("rejected", "fallback"),
}
WALL_MODELS = ("producer_cpu_if_wall", "acquisition_wall", "prefix_exit_wall")


def donor_arm(arm, *, whole):
    if whole:
        clock, prefetch = arm["process"]["clock"], arm["prefetch"]["prefetch"]
        slots = arm["prefetch"]["slots"]
    else:
        clock, prefetch = arm["clock"], arm["prefetch"]
        slots = arm["slots"]
    return {
        "clock": clock,
        "prefetch": prefetch,
        "slots": slots,
        "producer_cpu": prefetch["worker_cpu_ns"] / 1e9,
        "acquisition_wall": arm["receiver"]["wall_ns"] / 1e9,
        "prefix_exit_wall": clock["elapsed_s"],
    }


def donor_pair(doc, order, *, whole):
    by_role = {role: donor_arm(doc["arms"][arm], whole=whole) for role, arm in order}
    ordinary, slots = (by_role[role] for role in ("ordinary", "slots"))
    first, second = ordinary["prefetch"], slots["prefetch"]
    if (
        not first["hits"]
        or first["hit_bytes"] <= 0
        or any(first[key] != second[key] for key in ("hit_bytes", "hits", "submitted"))
        or any(a["clock"]["exit_code"] or a["prefetch"]["fallback"] for a in by_role.values())
        or ordinary["slots"]
        or not any(row.get("reuses") for row in slots["slots"])
    ):
        raise ValueError(
            "Each donor must compare matching complete lookahead in distinct slot modes"
        )
    return {
        "chronology": [role for role, _ in order],
        "ordinary": ordinary,
        "slots": slots,
        "delta_seconds": {
            metric: ordinary[metric] - slots[metric]
            for metric in ("producer_cpu", "acquisition_wall", "prefix_exit_wall")
        },
        "raw_bytes": doc["bytes" if whole else "waveform_bytes"],
        "hit_bytes": first["hit_bytes"],
        "windows": doc["windows"],
        "hit_count": first["hits"],
    }


def donors():
    body = checked(MEASUREMENTS / "prefetch-snapshot-0016.json.gz", DONOR_0016)
    weak = json.loads(gzip.decompress(body))
    prefix = json.loads(checked(MEASUREMENTS / "prefetch-prefix-0049.json", DONOR_0049))
    if not weak["qualified"] or weak["backing_waveform_bytes"] or weak["solver_children"]:
        raise ValueError("The 0016 original complete receiver-only donor is unavailable")
    return {
        "0016_ordinary_first": donor_pair(
            weak,
            (("ordinary", "fresh-1"), ("slots", "reuse-1")),
            whole=True,
        ),
        "0016_slots_first": donor_pair(
            weak,
            (("slots", "reuse-2"), ("ordinary", "fresh-2")),
            whole=True,
        ),
        "0049_ordinary_first": donor_pair(
            prefix["trials"]["forward"]["result"],
            (("ordinary", "ordinary-first"), ("slots", "slots-second")),
            whole=False,
        ),
        "0049_slots_first": donor_pair(
            prefix["trials"]["reverse"]["result"],
            (("slots", "slots-first"), ("ordinary", "ordinary-second")),
            whole=False,
        ),
    }


def enrolled_cases(snapshot, campaign):
    seal = json.loads(checked(snapshot / "rows-with-relocations-seal.json", FIRST_SEAL))
    fallback = json.loads(
        checked(MEASUREMENTS / "field-fallback-budget-first24.json", FALLBACK_PIN)
    )
    plan = json.loads(checked(snapshot / "plan.json", PLAN))
    order = [row["case"] for row in frozen_order(plan)[:24]]
    if seal["combined_sha256"] != FIRST or fallback["export"] != FIRST or order[-1] != "DS30-0147":
        raise ValueError("Expected the previously sealed first 24 comparisons")
    groups = {case: {} for case in order}
    for line in checked(snapshot / "rows-with-relocations.jsonl", FIRST).splitlines():
        row = json.loads(line)
        if row["case"] not in groups:
            continue
        arm = row["algorithm"]
        if (
            row["verified_pair"] is not True
            or not row["acquisition_verified"]
            or row.get("relocation_proof_sha256") != seal["proofs"].get(row["case"])
            or arm in groups[row["case"]]
        ):
            raise ValueError("Expected one verified arm with any required relocation seal")
        groups[row["case"]][arm] = row
    result = []
    for case, group in groups.items():
        stock, candidate = (group[role] for role in ("installed", "successor"))
        chron = sorted(group, key=lambda arm: group[arm]["child_started_unix_ns"])
        if (
            candidate["actual_order"] != chron
            or stock["actual_order"] != chron
            or group[chron[0]]["child_finished_unix_ns"] > group[chron[1]]["child_started_unix_ns"]
            or candidate["build_sha256"] != "sha256:" + BUILD
            or stock["build_sha256"] != "sha256:" + STOCK
        ):
            raise ValueError("Snapshot changed the original charged order or executable")
        detail = reconcile(campaign, stock, candidate)
        route, pins = fallback["routes"][case], fallback["receipts"][case]
        paid = {
            "elapsed_s": detail["decision_publication_s"],
            "cpu_s": detail["decision_publication_cpu_s"],
        }
        if (
            pins["candidate"] != detail["pins"]["result"]
            or pins["installed"] != stock["attempt_result_sha256"]
            or pins["witness"].removeprefix("sha256:") != detail["pins"]["scientific"]
            or any(
                route["rejected"][key] + route["fallback"][key]
                > min(paid[key], route["solve"][key])
                for key in paid
            )
        ):
            raise ValueError("Fallback components do not bind the same disjoint decision interval")
        detail["actual_child_wall_s"] = candidate["child_elapsed_s"]
        detail["fallback_route"] = route
        result.append(detail)
    return result


def transfer(delta, field_bytes, donor_bytes, cap):
    if (
        not all(isfinite(n) for n in (delta, field_bytes, donor_bytes, cap))
        or field_bytes < 0
        or donor_bytes <= 0
        or cap < 0
    ):
        raise ValueError("Invalid donor, field extent or paid stage cap")
    # A positive budget ceiling never erases a directly observed loss.
    return min(delta * field_bytes / donor_bytes, cap)


def project(row, donor):
    paid = row["work"]["prefetch"]
    delta = donor["delta_seconds"]
    acquisition = row["acquisition_s"] - row["native_detector_s"]
    exit_scope = (
        row["actual_child_wall_s"] - row["decision_publication_s"] - row["native_detector_s"]
    )
    worker = paid["worker_cpu_ns"] / 1e9
    bounds = {
        "producer_cpu": (delta["producer_cpu"], worker),
        "producer_cpu_if_wall": (delta["producer_cpu"], min(worker, acquisition)),
        "acquisition_wall": (delta["acquisition_wall"], acquisition),
        "prefix_exit_wall": (delta["prefix_exit_wall"], exit_scope),
    }
    return {
        name: transfer(saving, paid["hit_bytes"], donor["hit_bytes"], cap)
        for name, (saving, cap) in bounds.items()
    }


def remaining(rows, savings, common):
    def at(fraction):
        return gates(
            rows, [cost + fraction * pool for cost, pool in zip(savings, common, strict=True)]
        )

    def required(metric):
        if at(0.0)[metric] <= 0.5:
            return 0.0
        if at(1.0)[metric] > 0.5:
            return None
        lo, hi = 0.0, 1.0
        for _ in range(52):
            fraction = (lo + hi) / 2
            if at(fraction)[metric] <= 0.5:
                hi = fraction
            else:
                lo = fraction
        return hi

    by_sum, by_median = (required(metric) for metric in ("sum_ratio", "paired_median_ratio"))
    joint = None if None in (by_sum, by_median) else max(by_sum, by_median)
    budget = fsum(common)
    return {
        "eligible_s": budget,
        "sum_fraction": by_sum,
        "median_fraction": by_median,
        "joint_fraction": joint,
        "joint_s": None if joint is None else joint * budget,
    }


def scenario(rows, slot_credit, cost_keys, *, cpu=False):
    result = (
        rows
        if not cpu
        else [{"actual_wall_s": r["actual_cpu_s"], "stock_wall_s": r["stock_cpu_s"]} for r in rows]
    )
    field = "cpu_s" if cpu else "elapsed_s"
    remove = [
        slot + fsum(row["fallback_route"][key][field] for key in cost_keys)
        for row, slot in zip(rows, slot_credit, strict=True)
    ]
    info = gates(result, remove)
    info.update(
        summed_speedup=1 / info["sum_ratio"],
        paired_median_speedup=1 / info["paired_median_ratio"],
        both_at_half=info["sum_ratio"] <= 0.5 and info["paired_median_ratio"] <= 0.5,
        slot_saving=fsum(slot_credit),
        fallback_saving=fsum(remove) - fsum(slot_credit),
    )
    if not cpu:
        common = [
            max(
                0.0,
                row["acquisition_s"]
                + row["decision_publication_s"]
                - max(0.0, credit)
                - fsum(row["fallback_route"][key][field] for key in ("rejected", "fallback")),
            )
            for row, credit in zip(rows, slot_credit, strict=True)
        ]
        info["remaining_common_path"] = remaining(rows, remove, common)
    return info


def study(snapshot, campaign):
    rows = enrolled_cases(snapshot, campaign)
    base = {label: scenario(rows, [0] * len(rows), cost) for label, cost in TREATMENTS.items()}
    transfers = {}
    for name, donor in donors().items():
        saving = [project(row, donor) for row in rows]
        transfers[name] = {
            "donor": donor,
            "per_case": {row["case"]: values for row, values in zip(rows, saving, strict=True)},
            "scenarios": {
                name: {
                    label: scenario(
                        rows, [r[name] for r in saving], cost, cpu=name == "producer_cpu"
                    )
                    for label, cost in TREATMENTS.items()
                }
                for name in ("producer_cpu", *WALL_MODELS)
            },
        }
    return {
        "case_count": len(rows),
        "export_sha256": FIRST,
        "seal_sha256": FIRST_SEAL,
        "protocol_sha256": sha256(
            (HERE / "first24-slot-transfer-protocol.md").read_bytes()
        ).hexdigest(),
        "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "donor_pins": {"0016": DONOR_0016, "0049": DONOR_0049},
        "fallback_pin": FALLBACK_PIN,
        "baseline": base,
        "rows": rows,
        "transfers": transfers,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(study(args.snapshot, args.campaign), indent=2, sort_keys=True, allow_nan=False)
    )
