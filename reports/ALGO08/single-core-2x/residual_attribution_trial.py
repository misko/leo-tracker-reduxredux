"""Attribute the DS30-0155 selection change using four frozen saved-input solves."""

import argparse
import json
import os
import subprocess
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

CASE = "DS30-0155"
MODES = ("unchanged", "restore-primary", "restore-residual", "restore-all")
SPEC_SHA256 = "sha256:65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6"
REFERENCE_SHA256 = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), file=stream)


def rank(row):
    if not row["candidates"]:
        return None
    selected, = row["candidates"]
    value = selected["candidate_rank"]
    if type(value) is not int or value not in (0, 1):
        raise ValueError("Expected a native primary or residual rank")
    return value


def hybrids(baseline, candidate):
    from leo.contracts.digests import canonical_digest

    source = candidate["source"]
    base_rows, candidate_rows = baseline["source"]["probes"], source["probes"]
    raw = source["raw_recording_authority_digest"]
    if baseline["source"]["raw_recording_authority_digest"] != raw:
        raise ValueError("Expected matching raw recording authority")
    changed, transitions = [], Counter()
    available = {"restore-primary": [], "restore-residual": [], "restore-all": []}
    for before, after in zip(base_rows, candidate_rows, strict=True):
        if dict(before, candidates=[]) != dict(after, candidates=[]):
            raise ValueError("Selected probes differ in opportunity metadata or chronology")
        left, right = rank(before), rank(after)
        group = None
        if before["candidates"] != after["candidates"]:
            group = "restore-residual" if 1 in (left, right) else "restore-primary"
            transitions[f"{left}->{right}"] += 1
            changed.append(dict(visit=after["visit_index"], receiver=after["receiver_id"],
                                group=group, baseline_rank=left, candidate_rank=right))
        restored = dict(after, candidates=before["candidates"])
        for mode, rows in available.items():
            rows.append(restored if mode == group or mode == "restore-all" else after)

    detector = candidate["provenance"]["detector_sha256"].removeprefix("sha256:")
    results = {"unchanged": candidate}
    if canonical_digest(["cancellation", raw, detector, candidate_rows]) != (
        source["analysis_manifest_sha256"]
    ):
        raise ValueError("Candidate analysis digest does not bind the saved selections")
    for mode, rows in available.items():
        digest = canonical_digest(["cancellation", raw, detector, rows])
        results[mode] = dict(
            candidate, source=dict(source, probes=rows, analysis_manifest_sha256=digest),
            provenance=dict(candidate["provenance"], run_id="blind-compact-" + digest[7:39]),
        )
    return results, dict(changed=changed, transitions=dict(transitions))


def saved_native(pair_path, method, row):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore

    root = pair_path.parent / method
    receipt = row["receipt"]
    workspace = FastScanStore(root).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(workspace / "terminal.json")
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(native_path)
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or terminal["session_id"] != receipt["session_id"]
            or native["source"]["session_id"] != receipt["session_id"]
            or terminal["region"] != receipt["region"]
            or native["source"]["raw_recording_authority_digest"] != row["raw_authority"]):
        raise ValueError("Saved terminal or measurements differ from the paired receipt")
    return native


def worker(native_path, spec_path, archive, region, output, *, include_evidence=False):
    # The worker imports tools from the original freezer output. Install the
    # matched startup hook before importing its ordinary solver or storage.
    from tools.pipeline_eval.qualification import experimental_publication

    native, spec = read(native_path), read(spec_path)
    if spec.get("startup") == "lazy-exports":
        from tools.pipeline_eval.variants.experimental.lean_startup import install

        install()
    from leo.application.localization_v3_engine import _json_value
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan

    # The shims are for stages the trial never calls. All solver options,
    # data caches and numerical backend bindings come from the same freezer.
    solver_only = {
        k: v for k, v in spec.items()
        if k not in ("png_filter", "png_deflate", "paired_sha256")
    }
    solver_only.update(schedule="all", rendering="individual", ingress="stock", startup="stock")
    with TemporaryDirectory() as temp:
        root = Path(temp)

        def from_saved(recording, _root, assets, causal_archive, offer):
            if recording != root / "no-recording":
                raise ValueError("Expected the saved-detection solver callback")
            start_cpu, start_wall = process_time(), perf_counter()
            decision, packet, policy = algo08_position.solve(
                native, TleArchiveReader(causal_archive), assets, offer,
            )
            result = dict(
                status=decision["status"], reason=decision.get("reason"), arms=decision["arms"],
                orbit_policy=policy, solver_cpu_s=process_time() - start_cpu,
                solver_wall_s=perf_counter() - start_wall,
            )
            if packet is not None:
                result["owners"] = {arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS}
                result["associated"] = {arm: packet["arms"][arm]["associated_points"]
                                        for arm in ARMS}
                if include_evidence:
                    result["evidence"] = {k: packet[k] for k in (
                        "position_grid", "position_path", "objective_replay")}
            return result

        args = SimpleNamespace(recording=root / "no-recording", bulk_root=root,
                               archive=archive, region=region)
        with patch.object(algo08_scan, "analyze", from_saved):
            result = experimental_publication.run(args, solver_only)
    write(output, json.loads(json.dumps(result, default=_json_value, allow_nan=False)))


def run(pair_path, frozen, request_path, output):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import (
        archive_identity,
        verify_sources,
    )

    if pair_path.parent.name != CASE:
        raise ValueError(f"Expected the verified {CASE} development pair")
    pair_bytes = pair_path.read_bytes()
    pair = json.loads(pair_bytes)
    spec_path = frozen / "spec.json"
    specification = read(spec_path)
    if (canonical_digest(specification) != SPEC_SHA256
            or pair["candidate_specification_digest"] != SPEC_SHA256
            or specification != pair["candidate_specification"]
            or "failure" in pair):
        raise ValueError("Expected the completed pair and original frozen solver")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", specification["sources"])
    request = read(request_path)
    archive = request_path.parent / "tle"
    assigned = canonical_digest(request["causal_snapshots"])
    original_archive = pair["archive"]
    if (original_archive != archive_identity(archive)
            or original_archive["snapshots_sha256"] != assigned):
        raise ValueError("Expected the unchanged assigned causal archive")
    region = Path(pair["region"])
    offer = Algo08Region.parse(read(region)).document()
    if any(row["receipt"]["region"] != offer for row in pair["runs"].values()):
        raise ValueError("Saved pair did not use the requested regional offer")

    baseline, candidate = (saved_native(pair_path, arm, pair["runs"][arm])
                           for arm in ("baseline", "candidate"))
    inputs, partition = hybrids(baseline, candidate)
    if partition["transitions"] != {"0->None": 17, "1->None": 5, "None->0": 1, "None->1": 1}:
        raise ValueError("Expected the preregistered 24 lane selection changes")
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        mode: dict(
            native_sha256=canonical_digest(native),
            rows=len(native["source"]["probes"]),
            selected=sum(bool(row["candidates"]) for row in native["source"]["probes"]),
        )
        for mode, native in inputs.items()
    }
    write(output / "plan.json", dict(
        case=CASE, order=MODES, partition=partition, archive=pair["archive"], region=offer,
        specification_digest=SPEC_SHA256, pair_sha256=sha256(pair_bytes).hexdigest(),
        inputs=metadata,
    ))
    env = os.environ.copy()
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    env.update(PYTHONPATH=f"{frozen}:{RELEASE / 'src'}:{RELEASE}", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        frozen_offer = scratch / "offer.json"
        write(frozen_offer, offer)
        for mode in MODES:
            native_path, result_path = scratch / (mode + ".json"), output / (mode + ".json")
            write(native_path, inputs[mode])
            paths = (native_path, spec_path, archive, frozen_offer, result_path)
            subprocess.run([*command, *map(str, paths)], env=env, check=True, timeout=240)
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Causal archive changed during the four solves")
    # Endpoint evidence is first compared here, after every solve finished.
    results = {mode: read(output / (mode + ".json")) for mode in MODES}
    controls = {"unchanged": "candidate", "restore-all": "baseline"}
    diagnostics = {}
    for mode, arm in controls.items():
        if not controls_match(results[mode], pair["runs"][arm]):
            raise ValueError(f"{mode} did not reproduce both paired {arm} endpoints")
        diagnostics[mode] = dict(
            owners_equal=results[mode]["owners"] == pair["runs"][arm]["owners"],
            arm_metrics_equal=results[mode]["arms"] == pair["runs"][arm]["arms"],
        )
    write(output / "completed.json", dict(
        plan=read(output / "plan.json"), results=results, verified_controls=controls,
        control_diagnostics=diagnostics,
    ))


def controls_match(solved, published):
    return (solved["status"] == "ok" and published["receipt"]["decision"] == "complete"
            and all(solved["arms"][arm]["latlon"] == published["arms"][arm]["latlon"]
                    for arm in ARMS))


def score(completed_path, reference_path):
    from tools.pipeline_eval.scoring import distance_km

    completed = read(completed_path)
    controls = {"unchanged": "candidate", "restore-all": "baseline"}
    if (completed["plan"]["case"] != CASE or set(completed["results"]) != set(MODES)
            or completed["verified_controls"] != controls):
        raise ValueError("Expected all four completed solves and verified endpoint controls")
    raw = reference_path.read_bytes()
    if sha256(raw).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Expected the pinned scoring-only reference audit")
    match, = [r["reference"] for r in json.loads(raw)["cases"]
              if r["dataset_label"] == CASE and r["authority_eligible"]]
    reference = match["latitude_deg"], match["longitude_deg"]
    errors, effects = {}, {}
    for mode, result in completed["results"].items():
        errors[mode] = {arm: distance_km(result["arms"][arm]["latlon"], reference) for arm in ARMS}
    for arm in ARMS:
        a, b, c, d = (errors[mode][arm] for mode in MODES)
        effects[arm] = (
            None if None in (a, b, c, d)
            else dict(primary_km=b-a, residual_km=c-a, interaction_km=d-b-c+a,
                      restore_all_km=d-a)
        )
    return dict(completed, scoring=dict(reference_audit_sha256=REFERENCE_SHA256,
                                        horizontal_error_km=errors, effects=effects))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    commands = {
        "run": (run, ("pair_path", "frozen", "request_path", "output")),
        "worker": (worker, ("native_path", "spec_path", "archive", "region", "output")),
        "score": (score, ("completed_path", "reference_path")),
    }
    for action, (_, fields) in commands.items():
        command = actions.add_parser(action)
        for field in fields:
            command.add_argument(field, type=Path)
        if action == "worker":
            command.add_argument("--evidence", action="store_true")
    args = parser.parse_args()
    operation, fields = commands[args.action]
    options = dict(include_evidence=args.evidence) if args.action == "worker" else {}
    result = operation(*(getattr(args, field) for field in fields), **options)
    if args.action == "score":
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
