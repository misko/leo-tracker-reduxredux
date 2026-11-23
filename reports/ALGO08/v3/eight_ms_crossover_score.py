"""Audit the complete saved aperture crossover against its original raw publications."""

import argparse
from collections import Counter
import json
from pathlib import Path

from aperture_trial import ARMS, read, write
from dense_full_short_raw import checked
from eight_ms_crossover import BINDING_SHA, MARGIN, ORDER, PACKET_PINS, RAW_REPORT_PINS
from eight_ms_crossover import margin_packet, originals, projected, strata
from eight_ms_physical_score import quality
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from mixture_score import section
from north_factor_swap import rebound
from short_primary_epoch_audit import good_match
from signed_0374_transfer import owner_changes
from tools.pipeline_eval.qualification.paired_publication import evidence


HERE = Path(__file__).resolve().parent


def groups(graph, shared=None):
    rows = {}
    for track in graph["tracks"]:
        ids = frozenset(track["ids"])
        if shared is not None:
            ids &= shared
        if rows.keys() & ids:
            raise ValueError("Prepared graph assigned a signed observation twice")
        rows.update({oid: (ids, track["curved"]) for oid in ids})
    if shared is None and len(rows) != graph["graph_points"]:
        raise ValueError("Prepared graph assigned-point count changed")
    return rows


def graph_changes(base, candidate):
    before, after = groups(base).keys(), groups(candidate).keys()
    shared = before & after
    left, right = groups(base, shared), groups(candidate, shared)
    return dict(tracks=len(candidate["tracks"]), curved=sum(t["curved"] for t in candidate["tracks"]),
                graph_points=len(after), added=len(after-before), dropped=len(before-after), shared=len(shared),
                shared_changed_group=sum(left[oid][0] != right[oid][0] for oid in shared),
                shared_changed_curvature=sum(left[oid][1] != right[oid][1] for oid in shared),
                digest=canonical_digest(candidate))


def read_run(root, code, binding, result, native, classes, expected_grid):
    from full_short_physical_score import classified

    out = root / code
    clock = read(root / f"{code}-clock.json")
    proof = read(out / "joint-research-receipt.json")
    receipt = proof["receipt"]
    info = binding["inputs"][code]
    detector, = (out / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = FastScanStore(out).automatic_workspace(receipt["run_id"], create=False) / "terminal.json"
    found = evidence(out, receipt, 0, read_only=True)
    publication = json.loads(json.dumps(artifacts(out, receipt)))
    digest = canonical_digest(native)
    graph, = proof["solve"]["preparation"]
    if (clock["status"] != 0 or result["decision"] != "complete" or receipt["counts"] != result["counts"]
            or receipt["region"] != binding["request"]["offered_region"]
            or receipt["session_id"] != binding["request"]["session"]
            or found["raw_authority"] != binding["request"]["raw_authority"]
            or not proof["optimized_full_catalogue"]
            or proof["saved_handoff_manifest"] != binding["inventory"]
            or publication != proof["evidence"]
            or not digest == info["digest"] == proof["saved_digest"] == read(terminal)["native_sha256"]
            or canonical_digest(read(detector)) != digest
            or canonical_digest(read(Path(info["path"]))) != digest
            or native["provenance"]["detector_sha256"] != "sha256:" + info["recipe"]
            or info["researcher_derived"] != (code not in ("000", "111"))):
        raise ValueError(f"Saved handoff or publication failed validation for cell {code}")
    complete = receipt["decision"] == "complete"
    if complete:
        grid = FastStandardAnalysisStore(out).position_grid(receipt["run_id"])
        if (not grid["complete"] or grid["evaluated_points"] != expected_grid or len(publication["images"]) != 8
                or proof["solve"]["geographic_projector"]["calls"] <= 0):
            raise ValueError(f"Incomplete published science for cell {code}")
    owners = {}
    memberships = proof["selected_rows"]
    for arm, rows in memberships.items():
        selected = {oid: sat for oid, sat, _ in rows}
        if len(selected) != len(rows) or owner_digest(selected) != found["owners"][arm]:
            raise ValueError(f"Owner rows disagree with the standard publication for {code}")
        owners[arm] = dict(Counter(classes[oid] for oid in selected))
    prep = read(out / "graph-preparation-clock.json")
    solver = proof["solve"]
    measured = sum(item["cpu_s"] for item in prep)
    return dict(decision=receipt["decision"], reason=found["reason"], native=digest,
                terminal=receipt["terminal_sha256"], output=str(out), run_id=receipt["run_id"],
                process=clock, solve_cpu_s=solver["cpu_s"], solve_elapsed_s=solver["elapsed_s"],
                prep_cpu_s=measured, prep_calls=len(prep), post_prep_cpu_s=solver["cpu_s"]-measured,
                inference_clocks={k: v for k, v in (proof["route_details"] or {}).items() if k.endswith("_clocks")},
                regional_projection=solver["geographic_projector"], cold_catalogue_rows=solver["cold_track_rows"],
                grid_points=expected_grid if complete else 0, publication=publication, science=found["scientific_digests"],
                owner_sha256=found["owners"], owner_classes=owners, owner_roles=proof["selected_roles"],
                factor_counts=classified(native["source"]["probes"])["factors"], arms=found["arms"]), proof, graph


def score(root, crossover=None):
    binding = read(root / "binding.json")
    case = binding["case"]
    source, _, (twelve, eight) = originals(case)
    order = ["margin"] if crossover is not None else list(ORDER)
    if (binding["request"] != source["request"] or binding["inventory"] != source["inventory"]
            or binding["source_binding_sha256"] != BINDING_SHA[case] or binding["order"] != order):
        raise ValueError("Crossover did not use the frozen original recording and offer")
    archived = read(checked(HERE / f"measurements/eight-ms-{case}.json", RAW_REPORT_PINS[case]))
    reference = archived["runs"]
    rows = strata(twelve, eight)
    classes = {oid: ("shared_matched" if good_match(a, b) else "shared_changed") if kind == "shared" else kind
               for oid, kind, _, a, b in rows}
    if crossover is None and dict(Counter(kind for _, kind, *_ in rows)) != binding["strata"]:
        raise ValueError("Prepared diagnostic lane strata changed")
    publications = {}
    for code in order:
        if code in ("000", "111"):
            native = twelve if code == "000" else eight
        elif code == "margin":
            native = margin_packet(eight)
        else:
            native = rebound(twelve, projected(rows, code),
                             ["researcher-derived saved 8 ms factor crossover v1", PACKET_PINS[case], code])
        publications[code] = read_run(root, code, binding, reference["12ms"], native, classes, reference["12ms"]["grid_points"])
    if crossover is not None:
        return margin_score(binding, publications["margin"], rows, classes, archived, crossover)
    for code, name in (("000", "12ms"), ("111", "8ms")):
        row = publications[code][0]
        old = reference[name]
        if (row["native"] != old["native_sha256"] or row["terminal"] != old["terminal_sha256"]
                or row["arms"] != old["arms"] or row["owner_sha256"] != old["owner_sha256"]
                or row["science"] != old["scientific_digests"] or row["publication"]["images"] != old["publication"]["images"]):
            raise ValueError(f"Saved {name} control does not reproduce the original raw science")
    _, control, graph_control = publications["000"]
    controls = {name: reference[name]["errors_km"] for name in ("12ms", "v3")}
    for row, proof, graph in publications.values():
        row["position"] = section(row["arms"], archived["survey"], reference["v3"]["arms"])
        row["position_gate"] = quality({arm: row["position"]["arms"][arm]["error_km"] for arm in ARMS},
                                       controls, complete=row["decision"] == "complete")
        row["graph_vs_12ms"] = graph_changes(graph_control, graph)
        row["graph_classes"] = dict(Counter(classes[oid] for oid in groups(graph)))
        row["owner_vs_12ms"] = owner_changes(control, proof)
    return dict(case=archived["case"], binding=binding, lane_classes=dict(Counter(classes.values())),
                reference_receipt_sha256=RAW_REPORT_PINS[case], reference=archived["survey"], reference_errors_km=controls,
                runs={code: row for code, (row, _, _) in publications.items()})


def margin_score(binding, trial, rows, classes, archived, crossover):
    row, proof, graph = trial
    reference = archived["runs"]
    control = read(crossover / "111/joint-research-receipt.json")
    if (control["receipt"]["terminal_sha256"] != reference["8ms"]["terminal_sha256"]
            or control["saved_digest"] != reference["8ms"]["native_sha256"]
            or "margin_packet_clock" not in binding):
        raise ValueError("Margin guard did not use the original 8 ms control")
    controls = {name: reference[name]["errors_km"] for name in ("12ms", "v3")}
    if binding["case"] == "physical":
        controls["8ms"] = reference["8ms"]["errors_km"]
    row["position"] = section(row["arms"], archived["survey"], reference["v3"]["arms"])
    row["position_gate"] = quality({arm: row["position"]["arms"][arm]["error_km"] for arm in ARMS},
                                   controls, complete=row["decision"] == "complete")
    row["graph_vs_8ms"] = graph_changes(control["solve"]["preparation"][0], graph)
    row["graph_classes"] = dict(Counter(classes[oid] for oid in groups(graph)))
    row["owner_vs_8ms"] = owner_changes(control, proof)
    supplied = Counter(classes[oid] for oid, _, _, _, after in rows if after is not None)
    kept = Counter(classes[oid] for oid, kind, _, _, after in rows
                   if after is not None and (kind == "anchor" or after["fractional_margin"] >= MARGIN))
    return dict(case=archived["case"], binding=binding, fraction_margin=MARGIN, reference=archived["survey"],
                reference_errors_km=controls, shortlist={name: {"available": count, "kept": kept[name]}
                                                        for name, count in supplied.items()},
                reference_receipt_sha256=RAW_REPORT_PINS[binding["case"]], trial=row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--crossover", type=Path, help="Score a margin arm using the sealed crossover as control")
    args = parser.parse_args()
    write(args.output, score(args.root, args.crossover))
