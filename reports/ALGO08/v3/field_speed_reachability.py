"""Account for disjoint delivered DS30 timing stages using only sealed metadata."""

import argparse
import json
import tarfile
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import median

EXPORT = "90f434eca7d6fbefcf277568ab1a60a59826a82ea7cf774154e981a2d469e3b2"
PLAN = "9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
BUILD = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
SLOT_BUILD = "bb4d1466c6b3dbc3333ad3be71ce2dade103356fa5a8c6f5bb56bf599b66c282"
ARCHIVE = "4e9bc6d3d62cda6e915db62d28e4c114c82693b70768ba90bb258071fef015f5"
STOCK = "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
# Complete, resident 0016 reversed-order receiver-only donor. The byte-scaled
# transfer assumes every removed producer CPU second becomes a wall second.
DONOR_BYTES = 834_805_982
DONOR_SAVINGS = (0.797, 1.007)


def digest(data):
    return sha256(data).hexdigest()


def checked(path, pin):
    data = path.read_bytes()
    if digest(data) != pin.removeprefix("sha256:"):
        raise ValueError(f"Seal changed at {path}")
    return data


def load(path):
    data = path.read_bytes()
    return json.loads(data), digest(data)


def selected(snapshot):
    plan = json.loads(checked(snapshot / "plan.json", PLAN))
    build = json.loads(checked(snapshot / "build.json", BUILD))
    seal, seal_pin = load(snapshot / "rows-with-relocations-seal.json")
    if (
        seal["combined_sha256"] != f"sha256:{EXPORT}"
        or seal["plan_sha256"] != f"sha256:{PLAN}"
    ):
        raise ValueError(
            "The combined export seal must bind the enrolled plan and snapshot"
        )
    rows = [
        json.loads(line)
        for line in checked(
            snapshot / "rows-with-relocations.jsonl", EXPORT
        ).splitlines()
    ]
    cases = {}
    for row in rows:
        if not row["verified_pair"]:
            continue
        arm = row["algorithm"]
        expected = STOCK if arm == "installed" else BUILD
        if (
            row["build_sha256"] != f"sha256:{expected}"
            or row["elapsed_s"] <= 0
            or not row["acquisition_verified"]
        ):
            raise ValueError(
                "Expected the two fixed original-file builds and valid paired scope"
            )
        pair = cases.setdefault(row["case"], {})
        if arm in pair:
            raise ValueError("Duplicate arm in the final selected scope")
        pair[arm] = row
    if len(cases) != 20 or len(plan["cases"]) != 455:
        raise ValueError(
            "Expected both feasibility cases and the 18 verified original-file plan cases"
        )
    return seal_pin, build, [(p["installed"], p["successor"]) for p in cases.values()]


def source_provenance(snapshot, build):
    from io import BytesIO

    sources = build["sources"]
    with tarfile.open(
        fileobj=BytesIO(checked(snapshot / "source-archive.tar.gz", ARCHIVE)),
        mode="r:gz",
    ) as archive:
        for name, pin in sources.items():
            with archive.extractfile(name) as body:
                if digest(body.read()) != pin.removeprefix("sha256:"):
                    raise ValueError(
                        f"Frozen source archive does not authenticate {name}"
                    )
    slots = json.loads(checked(snapshot / "slot-build.json", SLOT_BUILD))
    changes = {
        name: pin for name, pin in slots["sources"].items() if sources.get(name) != pin
    }
    if (
        {key: value for key, value in slots.items() if key != "sources"}
        != {key: value for key, value in build.items() if key != "sources"}
        or set(changes)
        != {
            f"reports/ALGO08/v3/{name}.py"
            for name in (
                "integrated_original_batch",
                "prefetch_snapshots",
                "legacy_snapshot_reuse",
            )
        }
        or not set(sources) <= set(slots["sources"])
    ):
        raise ValueError(
            "Private lookahead option must preserve the exact rest of the delivered build"
        )
    return {
        "archive_sha256": ARCHIVE,
        "charter": build["charted_commit"],
        "sources": sources,
        "slot_build_sha256": SLOT_BUILD,
        "slot_build_source_changes": changes,
        "native": build["native"],
        "png": build["png"],
        "portable": build["portable_producer"],
    }


def reconcile(campaign, stock, candidate):
    for field in (
        "case",
        "assigned_rank",
        "raw_authority_sha256",
        "window_count",
        "actual_order",
    ):
        if stock[field] != candidate[field]:
            raise ValueError(f"Both measurements must bind the same original {field}")
    if stock["timing_scope"] != candidate["timing_scope"] and not (
        stock["outcome"] == "solver_failed"
        and stock["timing_scope"] == "raw_launch_to_exit"
    ):
        raise ValueError(
            "Expected comparable timing or the signed installed solver failure"
        )
    result_path = campaign / candidate["attempt"]
    if not result_path.resolve(strict=True).is_relative_to(campaign):
        raise ValueError("Expected the published local NVMe receipt")
    result = json.loads(checked(result_path, candidate["attempt_result_sha256"]))
    publication = result_path.parent / "publication"
    (
        (raw, raw_pin),
        (scientific, scientific_pin),
        (legacy, legacy_pin),
        (marker, marker_pin),
    ) = [
        load(publication / name)
        for name in (
            "unified-short-bootstrap.json",
            "exact-named-raw-witness.json",
            "legacy-original-acquisition.json",
            "algo08v3-successor-release.json",
        )
    ]
    raw_id = candidate["raw_authority_sha256"]
    if (
        raw["receiver_audit"]["recording_authority"] != raw_id
        or raw["native_sha256"] != result["native_sha256"]
        or legacy["finished_raw_authority"] != raw_id
        or legacy["authority_mode"] != "verified-once"
        or marker["build_sha256"] != f"sha256:{BUILD}"
        or marker["decision"] != candidate["outcome"]
        or marker["terminal_sha256"] != candidate["terminal_sha256"]
        or marker["authority_sha256"] != candidate["authority_sha256"]
        or raw["raw_acquisitions"] != 1
        or raw["verified_handoffs"] != 1
        or result["elapsed_s"] != candidate["elapsed_s"]
        or result["cpu_s"] != candidate["cpu_s"]
    ):
        raise ValueError(
            f"Candidate telemetry differs from the signed result for {candidate['case']}"
        )
    waveform = legacy["members"]
    if sum(m["windows"] for m in waveform) != candidate["window_count"]:
        raise ValueError("Verified-once input did not cover the whole original")
    phases = raw["phases"]
    acquire = phases["authenticated_raw_acquisition"]
    decision = phases["decision_and_publication"]
    native = raw["receiver_audit"]["native"]
    native_wall = sum(native["native_wall_ns"].values()) / 1e9
    if (
        acquire["elapsed_s"] < native_wall
        or acquire["elapsed_s"] + decision["elapsed_s"] > candidate["elapsed_s"]
    ):
        raise ValueError("The reported timings do not nest within their actual process")
    prefetch = raw["prefetch"]
    ports = scientific.get("ports") or {}
    timing = scientific.get("timing", {})
    portable = ports.get("portable", {})
    transfers = [item["counts"] for item in portable.get("transfers", [])]
    attempts = portable.get("attempts", [])
    acceleration = legacy.get("acceleration", {}).get("solver", {})
    grid = acceleration.get("grid") or {}
    history = ports.get("history_risk", {})
    slots = [
        min(prefetch["worker_cpu_ns"] / 1e9, prefetch["hit_bytes"] * n / DONOR_BYTES)
        for n in DONOR_SAVINGS
    ]
    work = {
        "original_members": len(waveform),
        "original_encoded_bytes": sum(m["encoded"] for m in waveform),
        "original_decoded_bytes": sum(m["decoded"] for m in waveform),
        "original_decode_wall_s": sum(m["native_read_wall_ns"] for m in waveform) / 1e9,
        "original_decode_process_cpu_s": sum(m["native_read_cpu_ns"] for m in waveform)
        / 1e9,
        "original_decoded_hash_wall_s": sum(m["hash_wall_ns"] for m in waveform) / 1e9,
        "original_decoded_hash_process_cpu_s": sum(m["hash_cpu_ns"] for m in waveform)
        / 1e9,
        "native_by_aperture": native["native_calls"],
        "prefetch": prefetch,
        "slots_conditional_wall_s": slots,
        "solver": {
            "route": history.get("choice", {}).get("route"),
            "cpu_s": sum(item["cpu_s"] for item in timing.get("solve", [])),
            "wall_s": sum(item["elapsed_s"] for item in timing.get("solve", [])),
            "render_cpu_s": sum(item["cpu_s"] for item in timing.get("render", [])),
            "render_wall_s": sum(
                item["elapsed_s"] for item in timing.get("render", [])
            ),
            "causal_preparation_cpu_s": sum(item["cpu_s"] for item in attempts),
            "causal_preparation_wall_s": sum(item["elapsed_s"] for item in attempts),
            "eligible_bodies": sum(item["bodies"] for item in attempts),
            "portable_hit_bodies": sum(
                item["sidecar_hit_bodies"] for item in transfers
            ),
            "portable_cold_bodies": sum(item["cold_bodies"] for item in transfers),
            "rank_cpu_s": sum(item["cpu_ns"] for item in ports.get("rank", [])) / 1e9,
            "grid_cpu_s": grid.get("clock", {}).get("cpu_ns", 0) / 1e9,
            "grid_points": grid.get("points", 0),
            "cairo_orbits": ports.get("cairo_layout", {}).get(
                "native_orbit_figures", 0
            ),
            "verified_pngs": ports.get("png", {}).get("verified", 0),
        },
    }
    return {
        "case": candidate["case"],
        "rank": candidate["assigned_rank"],
        "offered_order": candidate["actual_order"],
        "stock_outcome": stock["outcome"],
        "stock_timing_scope": stock["timing_scope"],
        "decision": candidate["outcome"],
        "stock_wall_s": stock["elapsed_s"],
        "stock_cpu_s": stock["cpu_s"],
        "actual_wall_s": candidate["elapsed_s"],
        "actual_cpu_s": candidate["cpu_s"],
        "acquisition_s": acquire["elapsed_s"],
        "acquisition_cpu_s": acquire["cpu_s"],
        "native_detector_s": native_wall,
        "native_detector_process_cpu_s": sum(native["native_cpu_ns"].values()) / 1e9,
        "decision_publication_s": decision["elapsed_s"],
        "decision_publication_cpu_s": decision["cpu_s"],
        "unassigned_s": candidate["elapsed_s"]
        - acquire["elapsed_s"]
        - decision["elapsed_s"],
        "validator_s": candidate["validator_elapsed_s"],
        "work": work,
        "pins": {
            "result": candidate["attempt_result_sha256"],
            "native": result["native_sha256"],
            "raw": raw_pin,
            "scientific": scientific_pin,
            "legacy": legacy_pin,
            "marker": marker_pin,
        },
    }


def gates(rows, savings):
    adjusted = [
        r["actual_wall_s"] - remove for r, remove in zip(rows, savings, strict=True)
    ]
    stock = [r["stock_wall_s"] for r in rows]
    return {
        "saving": sum(savings),
        "remaining": sum(adjusted),
        "sum_ratio": sum(adjusted) / sum(stock),
        "paired_median_ratio": median(a / b for a, b in zip(adjusted, stock)),
        "gap_to_half": sum(adjusted) - sum(stock) / 2,
    }


def report(snapshot, campaign):
    from reports.ALGO08.v3.full_successor_stage_budget import two_gate_reduction

    seal_pin, build, pairs = selected(snapshot)
    rows = [reconcile(campaign, a, b) for a, b in pairs]
    need = [
        {
            "installed_s": r["stock_wall_s"],
            "successor_s": r["actual_wall_s"],
            "acquisition_s": r["acquisition_s"],
            "native_detector_s": r["native_detector_s"],
            "decision_and_publication_s": r["decision_publication_s"],
        }
        for r in rows
    ]
    fields = (
        "stock_wall_s",
        "stock_cpu_s",
        "actual_wall_s",
        "actual_cpu_s",
        "acquisition_s",
        "acquisition_cpu_s",
        "native_detector_s",
        "native_detector_process_cpu_s",
        "decision_publication_s",
        "decision_publication_cpu_s",
        "unassigned_s",
        "validator_s",
    )
    values = {k: sum(r[k] for r in rows) for k in fields}
    prefetch = sum((Counter(r["work"]["prefetch"]) for r in rows), Counter())
    return {
        "export_sha256": EXPORT,
        "export_seal_sha256": seal_pin,
        "plan_sha256": PLAN,
        "build_sha256": BUILD,
        "sources": source_provenance(snapshot, build),
        "case_rows": rows,
        "totals": values,
        "prefetch": prefetch,
        "gates": gates(rows, [0] * len(rows)),
        "paired_budget": {
            scope: two_gate_reduction(need, scope)
            for scope in (
                "native_detector",
                "other_acquisition",
                "acquisition",
                "decision_and_publication",
                "acquisition_and_decision",
            )
        },
        "slot_sensitivity": [
            gates(rows, [r["work"]["slots_conditional_wall_s"][i] for r in rows])
            for i in range(2)
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.snapshot, args.campaign), indent=2, allow_nan=False))
