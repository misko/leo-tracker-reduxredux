"""External exact-output qualification for the owned application entry point.

Accepts either independently prepared inputs or native GLRT plus the read-only
causal archive. No scientific reference is read by the candidate process.
"""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np
from check_algo07v3_position import signed_snapshot
from check_algo07v3_scan_likelihood import fingerprint
from check_algo07v3_track_preparation import deny_legacy


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(inference, rendered):
    """Use the existing exact scientific comparator's established field scope."""
    p = inference["checkpoints"]
    replay = p["numerical"]["recovery"]
    gap = dict(p["gap"]["recovery"])
    gap["stages"] = [{k: v for k, v in row.items() if k != "seconds"} for row in gap["stages"]]
    additional = p["residual"]
    selected = additional["residual_context"]

    def science(value):
        if is_dataclass(value):
            return science(asdict(value))
        if isinstance(value, dict):
            return {k: science(v) for k, v in value.items() if k != "elapsed_seconds"}
        if isinstance(value, (tuple, list)):
            return [science(v) for v in value]
        return value

    result = {
        "initial": p["initial"]["initial_fit"],
        "recovery": p["conservative"]["conservative_fit"],
        "history_policy": p["family"]["family_fit"],
        "signed_policy": signed_snapshot(p["signed"]["signed_context"]),
        "cavity_nominations": p["cavity"]["nominations"],
        "cavity_policy": p["cavity"]["cavity_fit"],
        "recovery_inventory": p["inventory"]["inventory"],
        "predictive_recovery": p["predictive"]["recovery"],
        "numerical_recovery": {k: v for k, v in replay.items() if k != "stage_replay"},
        "gap_recovery": gap,
        "additional_recovery": dict(
            status=additional["status"],
            inventory=additional["residual_inventory"],
            preflight=additional["preflight"],
            selected_owners=p["gap"]["selected_state"]["owners"],
            families=[f.receipt for f in selected["families"]],
            replay_checks=selected["replay_checks"],
            recovery_complete=False,
        ),
        "residual_screen": p["residual_screen"],
        "additional_position": p["addition"],
        "reassociation_handoff": {k: v for k, v in p["incumbent"].items() if k != "context"},
        "reassociation_trigger": p["ranking"],
        "reassociation_screen": p["admission"],
        "reassociation_complete": p["final"],
    }
    result = {k: fingerprint(v) for k, v in result.items()}
    # This field deliberately remains an unfingerprinted policy receipt, as in
    # the existing comparison. Operational reuse timing alone is excluded.
    result["numerical_stage_replay"] = [
        {
            k: v
            for k, v in row.items()
            if k
            not in ("charged_original_seconds", "additional_logical_seconds", "reuse_wall_seconds")
        }
        for row in replay["stage_replay"]
    ]
    packet = rendered["packet"]
    result["presentation"] = dict(
        packet=fingerprint(science(packet)),
        products={
            name: hashlib.sha256(png).hexdigest() for name, png in rendered["products"].items()
        },
        grid_complete=packet["position_grid"]["complete"],
        grid_points=packet["position_grid"]["evaluated_points"],
    )
    return result


def run(args):
    bindings = {}

    def read(path, *, text=False):
        raw = Path(path).read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return raw.decode() if text else json.loads(raw)

    if args.native_input:
        # Owned operational adapters are loaded explicitly at this boundary;
        # the original strict legacy guard remains unchanged for execution.
        import leo.operations.localization_v3_history  # noqa: F401
        import leo.operations.localization_v3_inputs  # noqa: F401
        from leo.operations.tle_archive import TleArchiveReader

    sys.addaudithook(deny_legacy)
    from leo.analysis.localization_v3.reassociation_history import select_history
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import (
        ExecutionPorts,
        infer_prepared,
        render_inference,
        run_native,
    )

    def stage(name, operation):
        try:
            value = operation()
            print("recovery complete", name, flush=True)
            return True, value
        except Exception as error:
            print("recovery failed", name, type(error).__name__, str(error), flush=True)
            return False, None

    def gap_stage(name, operation, cap):
        began = time.monotonic()
        value = operation()
        if time.monotonic() - began >= cap:
            raise TimeoutError("gap operation exceeded its cap")
        return True, value

    execution = ExecutionPorts(stage, gap_stage, lambda: True, lambda _: None, time.monotonic)
    def progress(row):
        print("stage", json.dumps(row), flush=True)
    region = SearchRegion(tuple(args.search_center))
    started = time.monotonic()
    if args.native_input:
        native = read(args.native_input)
        if "sha256:" + bindings[str(args.native_input)] != args.input_sha256:
            raise ValueError("Native GLRT input binding differs")
        config = TrackConfig(**read(args.track_config)["config"])
        rendered = run_native(
            native,
            TleArchiveReader(args.tle_root),
            config,
            region,
            identities=args.scan_identities,
            execution=execution,
            screen_latitude_deg=args.screen_center[0],
            screen_longitude_deg=args.screen_center[1],
            title="ALGO07v3 standalone qualification",
            on_stage=progress,
        )
        inference = rendered["inference"]
    else:
        source = args.prepared
        summary = read(source / "summary.json")
        for name, sha in summary["source_files"].items():
            if digest(source / name) != sha:
                raise ValueError("Prepared input binding differs: " + name)
            bindings[str(source / name)] = sha
        with np.load(source / "bank.npz") as bank:
            sky = dict(bank=dict(bank))
        for name in (
            "previous_receipt",
            "genuine_previous_receipt",
            "nominal_elements",
            "metadata",
        ):
            sky[name] = read(source / (name + ".json"))
        for name in ("previous", "genuine_previous"):
            sky[name + "_tle"] = read(source / (name + ".tle"), text=True)
        prepared = dict(
            status=summary["status"],
            tracks=read(source / "tracks.json"),
            sky=sky,
            noise=read(source / "radio_noise.json"),
            phase_history=read(source / "phase_history.json"),
            phase_forecast=read(source / "phase_forecast.json"),
        )
        catalogue = read(args.recovery_catalogue)

        def history(request):
            if args.history_bank is None:
                raise ValueError("Admitted candidate requires --history-bank")
            return select_history(read(args.history_bank), request)

        inference = infer_prepared(
            prepared,
            region,
            catalogue,
            identities=args.scan_identities,
            collect_history=history,
            execution=execution,
            on_stage=progress,
        )
        rendered = render_inference(
            inference,
            title="ALGO07v3 standalone qualification",
            clock=time.monotonic,
            on_stage=progress,
        )
    engine_seconds = time.monotonic() - started
    result = snapshot(inference, rendered)
    for name, png in rendered["products"].items():
        (args.output / (name + ".png")).write_bytes(png)
    for name, value in (
        ("position-grid", rendered["packet"]["position_grid"]),
        ("position-path", rendered["packet"]["position_path"]),
    ):
        (args.output / (name + ".json")).write_text(json.dumps(value, allow_nan=False) + "\n")
    with (args.output / "result.json").open("x") as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    for path, sha in bindings.items():
        if digest(path) != sha:
            raise ValueError("Input changed during execution: " + path)
    modules = {
        name: dict(path=module.__file__, sha256=digest(module.__file__))
        for name, module in sys.modules.items()
        if getattr(module, "__file__", None)
        and ("/src/leo/" in str(module.__file__) or name.startswith("check_algo07v3_"))
    }
    receipt = dict(
        scope="native_to_png" if args.native_input else "prepared_to_png",
        seconds=time.monotonic() - started,
        engine_seconds=engine_seconds,
        stage_timings=rendered["stage_timings"],
        inputs=bindings,
        modules=modules,
        tool=dict(path=str(Path(__file__).resolve()), sha256=digest(__file__)),
        output_sha256=digest(args.output / "result.json"),
        search_center=args.search_center,
        scan_identities=args.scan_identities,
        archive_root=str(args.tle_root) if args.native_input else None,
        publication_qualified=False,
        full_pipeline_parity=False,
        execution_policy="qualification: all declared work; unchanged local gap/addition budgets",
    )
    (args.output / "result.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {k: receipt[k] for k in ("scope", "seconds", "engine_seconds", "output_sha256")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepared", type=Path)
    mode.add_argument("--native-input", type=Path)
    parser.add_argument("--input-sha256")
    parser.add_argument("--track-config", type=Path)
    parser.add_argument("--tle-root", type=Path)
    parser.add_argument("--screen-center", nargs=2, type=float, default=(37.5, -122.0))
    parser.add_argument("--recovery-catalogue", type=Path)
    parser.add_argument("--history-bank", type=Path)
    parser.add_argument("--search-center", nargs=2, type=float, required=True)
    parser.add_argument("--scan-identities", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.native_input and not all((args.input_sha256, args.track_config, args.tle_root)):
        parser.error("Native mode requires input hash, track config and read-only TLE root")
    if args.prepared and args.recovery_catalogue is None:
        parser.error("Prepared mode requires recovery catalogue")
    args.output.mkdir(parents=True, exist_ok=False)
    run(args)
