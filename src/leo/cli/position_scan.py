"""Bounded v6 position capture, native IQ chunks and a separate run envelope."""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

from leo.acquisition.position_scan_ppu import position_window
from leo.contracts.digests import canonical_digest
from leo.contracts.position_scan import PositionRunCheckpointV1
from leo.scanner.position_scan import PositionScanConfiguration, position_targets
from leo.scanner.short_window_recording import json_metadata
from leo.storage.continuous_window import ContinuousWindowWriter, run_path, write_checkpoint


def record_position_run(
    root: Path,
    run_id: str,
    host: str,
    serial: str,
    *,
    duration: float = 60,
    gain_db: float = 40,
    dry_run: bool = False,
    capture_function=None,
    before_start_hook=None,
) -> dict:
    if not 0 < duration <= 1800 or not host or not serial:
        raise ValueError(
            "explicit radio identity and a capture bound of at most 30 minutes required"
        )
    configuration = PositionScanConfiguration(targets=position_targets(), gain_db=gain_db)
    fields = json_metadata(dataclasses.asdict(configuration))
    path = run_path(root, run_id)
    preview = {
        "kind": "position_scan_preview",
        "configuration": fields,
        "configuration_sha256": canonical_digest(fields),
        "duration_s": duration,
        "analysis_path": "interior-position",
        "run_id": run_id,
    }
    if dry_run:
        return preview
    if capture_function is None:
        from pluto_plus.position_scan_record import FREQUENCIES, record_position_scan

        if tuple(target.if_center_hz for target in configuration.targets) != FREQUENCIES:
            raise ValueError("tracker and companion position plans disagree")
        capture_function = record_position_scan
    path.mkdir(parents=True, exist_ok=False)
    native = path / "native"
    native.mkdir()
    writer = ContinuousWindowWriter(
        native, run_id, configuration, radio={"host": host, "serial": serial}
    )
    state = PositionRunCheckpointV1(
        run_id=run_id,
        host=host,
        serial=serial,
        state="starting",
        configuration=fields,
        configuration_sha256=canonical_digest(fields),
        updated_utc_ns=time.time_ns(),
    ).model_dump(mode="json")

    def publish():
        state["updated_utc_ns"] = time.time_ns()
        write_checkpoint(path, PositionRunCheckpointV1(**state))

    def save(item, plan):
        window = position_window(item, configuration)
        writer.append(**window)
        state["state"] = "running"
        state["captured_windows"] += 1
        state["durable_windows"] = writer.durable_windows
        state["latest_targets"][window["target_id"]] = json_metadata(
            {
                "acquisition": window["acquisition"],
                "powers": window["powers"],
            }
        )
        # Bound checkpoint I/O to one sweep; native IQ persistence is independent.
        if item.record.visit % 24 == 23:
            publish()

    publish()
    try:
        capture = capture_function(
            host if host.startswith("ip:") else f"ip:{host}",
            serial,
            path / "wire",
            duration=duration,
            gain_db=gain_db,
            on_visit=save,
            before_start_hook=before_start_hook,
        )
        publication = writer.finish(stop_reason="explicit_stop")
        state.update(
            state="stopped",
            durable_windows=publication["durable_windows"],
            device_terminal=capture["terminal"],
            host_restoration=capture["host_restoration"],
        )
        publish()
    except BaseException as error:
        state.update(state="failed", fault=repr(error))
        try:
            publication = writer.finish(stop_reason="fault", failure=repr(error))
            state["durable_windows"] = publication["durable_windows"]
        finally:
            publish()
        raise
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--gain-db", type=float, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            record_position_run(
                args.root,
                args.run_id,
                args.host,
                args.serial,
                duration=args.duration,
                gain_db=args.gain_db,
                dry_run=args.dry_run,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
