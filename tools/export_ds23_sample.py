"""Snapshot the sealed random DS23 sample through existing read-only inputs."""

import dataclasses
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "reports/2026_10_18_ds23_post_ds22"
OUTPUT = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run():
    # This operation is run with the same-repository deployed storage worktree
    # on PYTHONPATH. Only its public contract is serialized; analysis consumes
    # the frozen JSON through this checkout's pure adapters.
    import leo.storage.scanner_tracking_source as public_port

    sample_path = DATASET / "random_sample_10.json"
    sample = json.loads(sample_path.read_text())
    if "sha256:" + hashlib.sha256((DATASET / "manifest.json").read_bytes()).hexdigest() != (
        sample["manifest_sha256"]
    ):
        raise ValueError("sample is not bound to the frozen DS23 authority")
    OUTPUT.mkdir(exist_ok=True)
    write(OUTPUT / "export_protocol.json", dict(
        sample_sha256=hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        seed=sample["seed"], adapter="read-only tracking JSON or ScannerTrackingInputStore.load",
        public_port_source=str(Path(public_port.__file__)),
        public_port_sha256=hashlib.sha256(Path(public_port.__file__).read_bytes()).hexdigest(),
        no_new_acquisition_or_GLRT_analysis=True, outcome_based_substitutions=False))
    store = public_port.ScannerTrackingInputStore(Path("/srv/bulk/leo"),
                                                 adaptive_probe_stride_ms=120)
    coverage = []
    try:
        for member in sample["selected"]:
            case = member["dataset_label"]
            directory = OUTPUT / case
            directory.mkdir(exist_ok=True)
            receipt = directory / "input_receipt.json"
            if receipt.exists():
                coverage.append(json.loads(receipt.read_text()))
                continue
            start = time.monotonic()
            row = dict(case=case, recording_id=member["recording_id"],
                       recording_format=member["recording_format"], status="pending")
            try:
                if member["recording_format"] == "short_window_iq_recording":
                    if not member["tracking_inputs"]:
                        raise ValueError("existing fast tracking input unavailable")
                    source = min(member["tracking_inputs"], key=lambda r: r["path"])
                    raw = Path(source["path"]).read_bytes()
                    if "sha256:" + hashlib.sha256(raw).hexdigest() != source["sha256"]:
                        raise ValueError("frozen fast input changed")
                    row.update(adapter="fast_tracking_contract", source_path=source["path"])
                    (directory / "tracking.json").write_bytes(raw)
                elif member["recording_format"] == "starlink_adaptive_hop_iq":
                    tracking = store.load(member["recording_id"])
                    if tracking.session_id != member["recording_id"]:
                        raise ValueError("public port returned a different recording")
                    document = dataclasses.asdict(tracking)
                    document["timing"] = (tracking.timing.model_dump(mode="json")
                                          if tracking.timing else None)
                    write(directory / "tracking.json", document)
                    row.update(adapter="ScannerTrackingInputStore.load",
                               qualified=tracking.qualified)
                else:
                    raise ValueError("unsupported observation adapter: "
                                     + member["recording_format"])
                row.update(status="exported", tracking_sha256=hashlib.sha256(
                    (directory / "tracking.json").read_bytes()).hexdigest())
            except (ValueError, OSError, RuntimeError) as error:
                row.update(status="existing_analysis_unavailable_or_invalid",
                           reason=f"{type(error).__name__}: {error}")
            row["seconds"] = time.monotonic() - start
            write(receipt, row)
            coverage.append(row)
            write(OUTPUT / "coverage.json", coverage)
            print(json.dumps(row), flush=True)
    finally:
        store.close()
    write(OUTPUT / "coverage.json", coverage)


if __name__ == "__main__":
    run()
