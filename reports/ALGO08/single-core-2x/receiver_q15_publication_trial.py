"""Time one frozen Q15 publication and compare it with a saved conditional arm."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_scan import immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.freeze_publication import LAUNCHER
from tools.pipeline_eval.qualification.paired_publication import archive_identity, measure, verify_sources
from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_arms

from .compare_publications import verified


def probe_rows(output):
    file, = (output / "fast-scan-automatic-work").glob("*/detections.json")
    return json.loads(file.read_bytes())["source"]["probes"]


def compare(control_root, control, output, candidate):
    before, old = verified(control_root, control)
    after, new = verified(output, candidate)
    if (control["raw_authority"] != candidate["raw_authority"]
            or any(control["receipt"][key] != candidate["receipt"][key]
                   for key in ("region", "session_id", "window_count", "counts"))):
        raise ValueError("Publication used a different input, offer or admission")
    old_reasons, new_reasons = (row["receipt"]["conditional_residual"] for row in (control, candidate))
    old_reasons = {key: value for key, value in old_reasons.items() if key != "query_cpu_ns"}
    new_reasons = {key: value for key, value in new_reasons.items() if key != "query_cpu_ns"}
    old_probes, new_probes = probe_rows(control_root), probe_rows(output)
    changed_rows = []
    for a, b in zip(old_probes, new_probes, strict=True):
        if {k: v for k, v in a.items() if k != "candidates"} != {
                k: v for k, v in b.items() if k != "candidates"}:
            raise ValueError("Published lane order or probe metadata changed")
        if a["candidates"] != b["candidates"]:
            changed_rows.append(dict(
                visit=b["visit_index"], receiver=b["receiver_id"], channel=b["channel"],
                control_ranks=[f["candidate_rank"] for f in a["candidates"]],
                q15_ranks=[f["candidate_rank"] for f in b["candidates"]],
            ))
    actual = dict(
        control_native_sha256=old["detector_sha256"], candidate_native_sha256=new["detector_sha256"],
        authority=candidate["raw_authority"], probe_rows=len(new_probes),
        ordered_probes_equal=old_probes == new_probes,
        changed_rows=changed_rows,
        probe_sha256=[canonical_digest(rows) for rows in (old_probes, new_probes)],
        selected_common=(before & after).total(), selected_added=(after - before).total(),
        selected_lost=(before - after).total(), schedule_counts_equal=old_reasons == new_reasons,
        decision_equal=(control["receipt"]["decision"], control["reason"])
        == (candidate["receipt"]["decision"], candidate["reason"]),
        arms_equal=control["arms"] == candidate["arms"], owners_equal=control["owners"] == candidate["owners"],
        path_and_grid_equal=control["scientific_digests"] == candidate["scientific_digests"],
    )
    for entry in (control, candidate):
        if entry["receipt"]["decision"] != "complete" or tuple(p["name"] for p in entry["artifacts"]) != PLOTS:
            raise ValueError("Expected both calibration fixes and all eight ordered figures")
    actual["encoded_images_equal"] = {
        a["name"]: a == b for a, b in zip(control["artifacts"], candidate["artifacts"], strict=True)
    }
    actual["decoded_images"] = {
        name: dict(control=old["figures"][name], candidate=new["figures"][name],
                   equal=old["figures"][name] == new["figures"][name])
        for name in PLOTS
    }
    return actual


def run(control_pair, configuration, output, timeout):
    saved = json.loads(control_pair.read_bytes())
    if "failure" in saved:
        raise ValueError("Saved control did not publish")
    control_root, control = control_pair.parent / "candidate", saved["runs"]["candidate"]
    archive = saved["archive"]
    args = SimpleNamespace(recording=Path(saved["recording"]), region=Path(saved["region"]),
                           archive=Path(archive["root"]), timeout=timeout)
    if archive_identity(args.archive) != archive:
        raise ValueError("Assigned causal archive changed")
    spec = json.loads(configuration.read_bytes())
    launcher = configuration.parent / LAUNCHER
    verify_sources(launcher, spec["sources"])
    path = FastStandardAnalysisStore(control_root).position_path(control["receipt"]["run_id"])
    endpoints = {arm: row["endpoint"] for arm, row in path["stages"][-1]["arms"].items()}
    if bound_arms(endpoints, path["box_width_km"]) != []:
        raise ValueError("Expected verified saved endpoints strictly inside the regional guard")

    candidate = measure(launcher, output, args, configuration)
    immutable_json(output / "candidate-only-receipt.json", candidate)
    if archive_identity(args.archive) != archive:
        raise ValueError("Assigned causal archive changed during the run")
    verify_sources(launcher, spec["sources"])
    return dict(
        mode="one candidate-only run", saved_conditional_control=str(control_pair),
        specification=str(configuration), candidate_specification_digest=canonical_digest(spec),
        archive=archive, saved_control_endpoints_km=endpoints, run=candidate,
        comparison=compare(control_root, control, output, candidate),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control_pair", "configuration", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    print(json.dumps(run(**vars(parser.parse_args())), indent=2, allow_nan=False))
