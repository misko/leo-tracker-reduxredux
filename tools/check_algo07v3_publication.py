"""Native v3 to owned evidence and existing UI publication, outside production.

All-work qualification execution only; production cancellation/deadline behavior
is not qualified by this tool. The candidate reads no earlier scientific output.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from check_algo07v3_track_preparation import deny_legacy


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_snapshot(evidence, pngs):
    """Map real persisted evidence to the pre-existing exact comparison scope."""
    audit = dict(evidence["audit"])
    numerical = audit["numerical_recovery"]
    audit["numerical_recovery"] = {k: v for k, v in numerical.items() if k != "stage_replay"}
    gap = dict(audit["gap_recovery"])
    gap["stages"] = [{k: v for k, v in row.items() if k != "seconds"} for row in gap["stages"]]
    audit["gap_recovery"] = gap
    value = {k: fingerprint(v) for k, v in audit.items()}
    value["numerical_stage_replay"] = [
        {
            k: v
            for k, v in row.items()
            if k
            not in ("charged_original_seconds", "additional_logical_seconds", "reuse_wall_seconds")
        }
        for row in numerical["stage_replay"]
    ]

    def science(v):
        if isinstance(v, dict):
            return {k: science(w) for k, w in v.items() if k != "elapsed_seconds"}
        if isinstance(v, (list, tuple)):
            return [science(w) for w in v]
        return v

    packet = evidence["presentation"]
    value["presentation"] = dict(
        packet=fingerprint(science(packet)),
        products={name: hashlib.sha256(data).hexdigest() for name, data in pngs.items()},
        grid_complete=packet["position_grid"]["complete"],
        grid_points=packet["position_grid"]["evaluated_points"],
    )
    return value


def run(args):
    began = time.monotonic()
    # Public concrete ports are explicitly loaded at this operational boundary.
    import leo.operations.localization_v3_history  # noqa: F401
    import leo.operations.localization_v3_inputs  # noqa: F401
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_standard_analysis import RENDER_REVISION, FastStandardAnalysisStore
    from leo.storage.localization_v3 import LocalizationV3Store

    sys.addaudithook(deny_legacy)
    from dataclasses import asdict

    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import ExecutionPorts, run_native
    from leo.application.localization_v3_result import build_evidence, publish_saved
    from leo.contracts.digests import canonical_digest

    raw = args.native_input.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != args.input_sha256:
        raise ValueError("Native input hash differs")
    native = json.loads(raw)
    if native["source"]["session_id"] != args.session_id:
        raise ValueError("Native input session differs")
    config_bytes = args.track_config.read_bytes()
    config = TrackConfig(**json.loads(config_bytes)["config"])

    def stage(name, operation):
        value = operation()
        print("recovery complete", name, flush=True)
        return True, value

    def gap(name, operation, limit):
        start = time.monotonic()
        value = operation()
        if time.monotonic() - start >= limit:
            raise TimeoutError("Gap operation exceeded original cap")
        return True, value

    execution = ExecutionPorts(stage, gap, lambda: True, lambda _: None, time.monotonic)
    result = run_native(
        native,
        TleArchiveReader(args.tle_root),
        config,
        SearchRegion(tuple(args.search_center)),
        identities=args.scan_identities,
        execution=execution,
        screen_latitude_deg=args.screen_center[0],
        screen_longitude_deg=args.screen_center[1],
        title="ALGO07v3 standalone qualification",
        on_stage=lambda row: print("stage", json.dumps(row), flush=True),
    )
    rendered_at = time.monotonic()

    def sources():
        return {
            name: dict(path=m.__file__, sha256=digest(m.__file__))
            for name, m in sys.modules.items()
            if getattr(m, "__file__", None) and "/src/leo/" in str(m.__file__)
        }

    modules = sources()
    provenance = dict(
        configuration_sha256=canonical_digest(
            dict(
                track_config=asdict(config),
                search_center=args.search_center,
                screen_center=args.screen_center,
                scan_identities=args.scan_identities,
                execution="qualification-all-work",
                grid_seconds=300.0,
            )
        ),
        implementation_sha256=canonical_digest({k: v["sha256"] for k, v in modules.items()}),
        modules=modules,
    )
    evidence = build_evidence(
        result,
        identity=dict(
            run_id=args.run_id, session_id=args.session_id, input_sha256=args.input_sha256
        ),
        provenance=provenance,
        title="ALGO07v3 standalone qualification",
        renderer_revision=RENDER_REVISION,
    )
    projected_at = time.monotonic()
    scientific = LocalizationV3Store(args.output / "publication")
    public = FastStandardAnalysisStore(args.output / "publication")
    saved = scientific.save(evidence, result["products"])
    saved_at = time.monotonic()
    manifest = publish_saved(args.run_id, scientific, public)
    published_at = time.monotonic()
    # Publication is complete before expensive external comparison serialization.
    loaded = scientific.load(args.run_id)
    comparison = evidence_snapshot(loaded["evidence"], loaded["pngs"])
    for name, data in result["products"].items():
        if public.artifact(args.run_id, name) != data:
            raise ValueError("Published PNG differs from native renderer")
    grid, path = public.position_grid(args.run_id), public.position_path(args.run_id)
    if grid["binding"]["terminal_sha256"] != saved["sha256"]:
        raise ValueError("Grid binding differs")
    if path["binding"]["terminal_sha256"] != saved["sha256"]:
        raise ValueError("Path binding differs")
    if publish_saved(args.run_id, scientific, public) != manifest:
        raise ValueError("Idempotent publication differs")
    for source, sha in (
        (args.native_input, args.input_sha256[7:]),
        (args.track_config, hashlib.sha256(config_bytes).hexdigest()),
    ):
        if digest(source) != sha:
            raise ValueError("Input changed during publication")
    if sources() != modules:
        raise ValueError("Scientific source changed during publication")
    with (args.output / "result.json").open("x") as stream:
        json.dump(comparison, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    receipt = dict(
        scope="native_input_to_atomic_UI_manifest",
        modules=modules,
        inputs={
            str(args.native_input): args.input_sha256[7:],
            str(args.track_config): hashlib.sha256(config_bytes).hexdigest(),
        },
        tool=dict(path=str(Path(__file__).resolve()), sha256=digest(__file__)),
        output_sha256=digest(args.output / "result.json"),
        native_to_render_seconds=rendered_at - began,
        evidence_projection_seconds=projected_at - rendered_at,
        scientific_save_seconds=saved_at - projected_at,
        UI_publication_seconds=published_at - saved_at,
        native_to_publication_seconds=published_at - began,
        qualification_seconds=time.monotonic() - began,
        scientific_receipt=saved,
        publication=manifest,
        full_dataset_equivalence=False,
        production_execution_qualified=False,
        matched_complete_path_speedup=None,
    )
    (args.output / "result.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in ("output_sha256", "native_to_publication_seconds", "qualification_seconds")
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--track-config", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    parser.add_argument("--screen-center", nargs=2, type=float, default=(37.5, -122.0))
    parser.add_argument("--search-center", nargs=2, type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run(args)
