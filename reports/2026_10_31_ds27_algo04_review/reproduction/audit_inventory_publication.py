"""Audit cached discovery masks against published ownership; no fitting or truth."""

import argparse
import hashlib
import json
from pathlib import Path

from rank_native_residuals import canonical_tracks, published_owners


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def residual_support(track, associated):
    remaining = [(oid, float(t)) for oid, t in zip(track["observation_ids"], track["times"], strict=True)
                 if oid not in associated]
    times = sorted(t for _, t in remaining)
    return dict(points=len(remaining), span_s=times[-1] - times[0] if times else 0.0,
                maximum_gap_s=max((b - a for a, b in zip(times, times[1:])), default=0.0),
                large=len(remaining) >= 20 and times[-1] - times[0] >= 20 if times else False,
                observation_ids=sorted(oid for oid, _ in remaining))


def audit_case(tracks, observations, inventory, support, baseline, chosen=None):
    all_ids = {o["observation_id"] for o in observations}
    if len(all_ids) != len(observations):
        raise ValueError("Duplicate native observation identity")
    canonical = canonical_tracks(tracks)
    graph_ids = {oid for _, t, _ in canonical for oid in t["observation_ids"]}
    if not graph_ids <= all_ids:
        raise ValueError("Unknown graph observation")
    result = {}
    for arm in ("c0", "fitted_c"):
        pub = published_owners(baseline, arm)
        verified = support["arms"][arm]
        if not support["all_verified"] or set(verified["owners"]) != set(pub):
            raise ValueError("Publication support does not match actual ALGO02 gates")
        if any(pub[oid] is not None and pub[oid] != owner for oid, owner in verified["owners"].items()):
            raise ValueError("Published ALGO02 owner mismatch")
        proposed = set(inventory["policy"][arm]["proposed_associated_ids"])
        unreported = set(verified["unreported_postfit_ids"])
        if not set(pub) <= proposed or unreported != proposed - set(pub):
            raise ValueError("Unreported postfit support does not partition replay mask")
        if not proposed <= all_ids:
            raise ValueError("Unknown inventory-owned observation")
        actual = published_owners(chosen, arm) if chosen is not None else None
        if actual is not None and not set(actual) <= all_ids:
            raise ValueError("Unknown chosen ALGO04 owner")
        inventory_rows = [r for r in inventory["tracks"] if r["arm"] == arm]
        long_rows = []
        total_published_long_sources = 0
        for index, track, variants in canonical:
            published_residual = residual_support(track, pub)
            if not published_residual["large"]:
                continue
            total_published_long_sources += 1
            variant_indices = {v["track_index"] for v in variants}
            saved = [r for r in inventory_rows if r["track_index"] in variant_indices]
            saved_ids = {oid for r in saved for oid in r["observation_ids"]}
            replay_residual = residual_support(track, proposed)
            missing_ids = set(published_residual["observation_ids"]) - saved_ids
            if missing_ids != set(track["observation_ids"]) & unreported:
                raise ValueError("Inventory residual discrepancy extends beyond unreported postfit support")
            if not missing_ids:
                continue
            actual_residual = residual_support(track, actual) if actual is not None else None
            long_rows.append(dict(track_index=index, key=track["key"], source_variants=variants,
                quality_status=track.get("quality_status"), native_points=len(track["observation_ids"]),
                native_span_s=max(track["times"]) - min(track["times"]),
                published_ALGO02_residual=published_residual, replay_inventory_residual=replay_residual,
                chosen_ALGO04_residual=actual_residual, absent_from_inventory=not saved,
                suppressed_below_large_threshold=not replay_residual["large"],
                missing_from_inventory_ids=sorted(missing_ids),
                missing_ids_still_unassociated_ALGO04=sorted(missing_ids - set(actual)) if actual is not None else None))
        result[arm] = dict(total_GLRT=len(all_ids), published_ALGO02_associated=len(pub),
            replay_inventory_proposed_associated=len(proposed), unreported_postfit_points=len(unreported),
            unreported_postfit_ids=sorted(unreported),
            unreported_postfit_outside_graph=len(unreported - graph_ids),
            published_ALGO02_unassociated=len(all_ids - set(pub)),
            replay_inventory_unassociated=len(all_ids - proposed),
            chosen_ALGO04_associated=len(actual) if actual is not None else None,
            chosen_ALGO04_unassociated=len(all_ids - set(actual)) if actual is not None else None,
            unreported_still_unassociated_ALGO04=len(unreported - set(actual)) if actual is not None else None,
            unreported_associated_ALGO04=len(unreported & set(actual)) if actual is not None else None,
            long_native_curves_under_published_ALGO02=total_published_long_sources,
            long_native_curves_with_missing_inventory_ids=len(long_rows),
            long_native_curves_absent_from_inventory=sum(r["absent_from_inventory"] for r in long_rows),
            long_native_curves_suppressed_below_large_threshold=sum(r["suppressed_below_large_threshold"] for r in long_rows),
            long_native_curves_still_large_unassociated_ALGO04=sum(
                r["chosen_ALGO04_residual"]["large"] for r in long_rows) if actual is not None else None,
            long_native_curves=long_rows)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, default=Path("/srv/bulk/leo-dev/fast-algo02-production-v1"))
    parser.add_argument("--allow-in-progress", action="store_true")
    args = parser.parse_args()
    study = args.study
    index_path = study / "analysis-index.json"
    seal_path = study / "analysis-seal.json"
    if not (index_path.exists() and seal_path.exists()) and not args.allow_in_progress:
        raise ValueError("Need sealed final chosen-ALGO04 index")
    input_map = read(study / "public-input-map.json")
    if input_map["dataset_manifest_sha256"] != digest(study / "dataset/manifest.json"):
        raise ValueError("Input roster belongs to a different frozen acquisition manifest")
    roster = input_map["rows"]
    if len(roster) != 15 or len({r["case"] for r in roster}) != 15:
        raise ValueError("Need all 15 distinct frozen fast cases")
    source_hashes = {str(Path(__file__)): digest(__file__),
                     str(Path(__file__).with_name("rank_native_residuals.py")): digest(Path(__file__).with_name("rank_native_residuals.py")),
                     str(study / "public-input-map.json"): digest(study / "public-input-map.json")}
    index = None
    if index_path.exists() and seal_path.exists():
        seal = read(seal_path)
        if seal["analysis_index_sha256"] != digest(index_path):
            raise ValueError("Changed sealed analysis index")
        if (seal["dataset_manifest_sha256"] != input_map["dataset_manifest_sha256"]
                or seal.get("all_fast_terminal") is not True or seal.get("no_GPS") is not True):
            raise ValueError("Analysis seal does not bind final causal DS27 membership")
        index = {r["case"]: r for r in read(index_path)["cases"]}
        if set(index) != {r["case"] for r in roster}:
            raise ValueError("Analysis index omits frozen fast cases")
        source_hashes[str(index_path)] = digest(index_path)
        source_hashes[str(seal_path)] = digest(seal_path)
    cases = []
    for entry in roster:
        label = entry["case"]
        folder = study / "cases" / label
        recovery = folder / "candidate-v2/recovery"
        descriptor_path = recovery / "snapshot/descriptor.json"
        if not descriptor_path.exists():
            cases.append(dict(case=label, state="snapshot_unavailable", reason=entry.get("reason", "no completed public snapshot")))
            continue
        descriptor = read(descriptor_path)
        paths = sorted((recovery / "all-large-track-recovery").glob("*/inventory.json"))
        if len(paths) != 1:
            raise ValueError("Expected one discovery inventory: " + label)
        inv_path = paths[0]
        support_path = inv_path.with_name("publication_support.json")
        support_doc = read(support_path)
        for path in (inv_path, descriptor_path):
            if support_doc["source_receipts"].get(str(path)) != digest(path).removeprefix("sha256:"):
                raise ValueError("Publication-support receipt changed: " + str(path))
        root = Path(descriptor["root"])
        tracks_path = root / "SCAN/tracks.json"
        observations_path = root / "SCAN/observations.json"
        for path in [tracks_path, observations_path]:
            if digest(path) != descriptor["files"][str(path.relative_to(root))]:
                raise ValueError("Changed native snapshot: " + str(path))
        chosen_path = None
        if index is not None:
            row = index[label]
            if row["state"] == "complete":
                chosen_path = Path(row["terminal_path"])
                if digest(chosen_path) != row["terminal_sha256"]:
                    raise ValueError("Changed chosen terminal")
        elif (folder / "candidate-v3/terminal.json").exists():
            chosen_path = folder / "candidate-v3/terminal.json"
        chosen = read(chosen_path) if chosen_path is not None else None
        if chosen is not None and chosen["incumbent"]["baseline"] != descriptor["terminal"]:
            raise ValueError("Chosen ALGO04 embeds a different ALGO02 baseline")
        result = audit_case(read(tracks_path), read(observations_path), read(inv_path),
                            support_doc, descriptor["terminal"], chosen)
        cases.append(dict(case=label, state="audited", chosen_ALGO04_available=chosen is not None, arms=result))
        for path in [descriptor_path, inv_path, support_path, tracks_path, observations_path] + ([chosen_path] if chosen_path else []):
            source_hashes[str(path)] = digest(path)
        inventory_receipt = recovery / "inventory-receipt.json"
        if inventory_receipt.exists():
            source_hashes[str(inventory_receipt)] = digest(inventory_receipt)
            command = read(inventory_receipt)["command"]
            scripts = [Path(v) for v in command if v.endswith("/algo03_inventory.py")]
            for script in scripts:
                for name in ("algo03_inventory.py", "inventory_all_large_tracks.py", "benchmark_graph_covariance.py", "inventory_cohort_unassociated.py"):
                    path = script.with_name(name)
                    source_hashes[str(path)] = digest(path)
    for name in ("algo03_inventory.py", "inventory_all_large_tracks.py", "benchmark_graph_covariance.py", "inventory_cohort_unassociated.py"):
        path = args.checkout / "tools" / name
        source_hashes[str(path)] = digest(path)
    totals = {}
    fields = ("total_GLRT", "published_ALGO02_associated", "replay_inventory_proposed_associated",
              "unreported_postfit_points", "unreported_still_unassociated_ALGO04", "unreported_associated_ALGO04",
              "long_native_curves_under_published_ALGO02",
              "long_native_curves_with_missing_inventory_ids", "long_native_curves_absent_from_inventory",
              "long_native_curves_suppressed_below_large_threshold", "long_native_curves_still_large_unassociated_ALGO04")
    for arm in ("c0", "fitted_c"):
        rows = [r["arms"][arm] for r in cases if r["state"] == "audited"]
        totals[arm] = {field: sum(r[field] for r in rows if r[field] is not None) for field in fields}
        totals[arm]["chosen_support_available_cases"] = sum(r["chosen_ALGO04_associated"] is not None for r in rows)
    explanation = (
        "algo03_inventory.run() calls inventory_all_large_tracks.one() before publication_support(). "
        "For baseline jobs, one() obtains baseline_pair() replay proposed_associated_ids, including postfit-only IDs; "
        "it subtracts that replay mask before creating residual rows, omitting a native source if both current and earlier "
        "residual support have fewer than two points. publication_support() subsequently restricts owners to actual "
        "published ALGO02 gates and records replay-only IDs as unreported_postfit_ids, but does not rebuild inventory.json. "
        "The proposed/postfit-only distinction is explicit in the replay schema; inventory.summary.associated is "
        "therefore a replay/proposed count, not the published terminal count. Treating its residual "
        "inventory as the residual of published ownership suppresses unpublished support. This audit establishes an "
        "accounting/discovery-mask discrepancy, not that any replay-only ID meets acceptance gates or should be associated."
    )
    report = dict(schema="ds27-inventory-publication-audit/v1", sealed_final_chosen_index=index is not None,
        no_GPS_truth_read=True, no_fitting_or_inference=True, thresholds=dict(points=20, span_s=20,
        gap_policy="whole native source support span; maximum gap retained, not a contiguous-fragment ranking"),
        audited_cases=sum(r["state"] == "audited" for r in cases), totals=totals,
        explanation=explanation, source_sha256=source_hashes, cases=cases)
    report["code_evidence"] = [
        dict(path=str(args.checkout / "tools/algo03_inventory.py"), line=33,
             finding="Inventory is built before published support is computed at line44 and written separately at line45."),
        dict(path=str(args.checkout / "tools/inventory_all_large_tracks.py"), line=130,
             finding="Baseline replay mask is selected; proposed_associated_ids are subtracted before source rows are built."),
        dict(path=str(args.checkout / "tools/benchmark_graph_covariance.py"), line=68,
             finding="Replay membership becomes proposed_associated_ids, with postfit_only_points separately labelled."),
    ]
    (study / "inventory-publication-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# DS27 discovery inventory versus published ownership", "", explanation, "",
        f"All 15 fast cases retained; {report['audited_cases']} available snapshots audited. "
        f"Final chosen index sealed: {index is not None}. No fitting, GPS-truth read or inference run.", "",
        "| Case | Arm | Published ALGO02 | Replay proposed | Replay-only IDs | Still unassociated ALGO04 | Long native sources absent |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in cases:
        if row["state"] != "audited":
            lines.append(f"| {row['case']} | — | unavailable | — | — | — | — |")
            continue
        for arm, values in row["arms"].items():
            lines.append(f"| {row['case']} | {arm} | {values['published_ALGO02_associated']} | "
                f"{values['replay_inventory_proposed_associated']} | {values['unreported_postfit_points']} | "
                f"{values['unreported_still_unassociated_ALGO04']} | {values['long_native_curves_absent_from_inventory']} |")
    lines += ["", "Omitted or suppressed native sources, shown once using fitted-c ownership:", "",
        "| Case | Native source | Missing IDs | Published residual span (s) | Maximum gap (s) | Existing graph quality | Chosen residual IDs |",
        "|---|---|---:|---:|---:|---|---:|"]
    for case in cases:
        if case["state"] != "audited":
            continue
        for row in case["arms"]["fitted_c"]["long_native_curves"]:
            residual = row["published_ALGO02_residual"]
            chosen = row["chosen_ALGO04_residual"]
            lines.append(f"| {case['case']} | {row['key']} | {len(row['missing_from_inventory_ids'])} | "
                f"{residual['span_s']:.6f} | {residual['maximum_gap_s']:.6f} | {row['quality_status']} | "
                f"{chosen['points'] if chosen is not None else 'unknown'} |")
    lines += ["", "Precise code path: `tools/algo03_inventory.py:33` builds the inventory before "
        "`:44–45` computes/writes publication support; `tools/inventory_all_large_tracks.py:130–140` "
        "selects/subtracts replay ownership; `tools/benchmark_graph_covariance.py:68–70` explicitly labels postfit-only "
        "and proposed IDs. Both the checkout and runtime script hashes are recorded in the JSON.", "",
        "Whole-source long-curve thresholds are at least 20 residual native IDs spanning at least 20 seconds; "
        "gaps are reported rather than bridged into a claimed continuous emitter. The JSON lists omitted/suppressed sources, "
        "exact IDs, chosen residual support and all input/source hashes. No acceptance or emitter-identity claim follows from a long graph curve.", ""]
    (study / "inventory-publication-audit.md").write_text("\n".join(lines))
    print(json.dumps(dict(audited_cases=report["audited_cases"], sealed=index is not None, totals=totals)))


if __name__ == "__main__":
    main()
