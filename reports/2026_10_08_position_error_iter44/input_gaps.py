"""Read-only source readiness for every pending member without a compatible baseline."""

import json
from pathlib import Path

from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent


def main():
    destination = HERE / "input-gaps.json"
    if destination.exists():
        raise FileExistsError(destination)
    inputs = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    output = []
    try:
        for row in json.loads((HERE / "readiness.json").read_text())["members"]:
            member = row["member"]
            if member["evaluation_status"] != "pending" or row["baseline_status"] == "compatible":
                continue
            item = dict(member=member, baseline_status=row["baseline_status"])
            try:
                source = inputs.load(member["session_id"])
                item.update(status="tracking_inputs_ready", probes=len(source.probes),
                            input_digest=source.input_manifest_sha256,
                            analysis_digest=source.analysis_manifest_sha256)
                assert source.input_manifest_sha256 == member["recording_manifest_sha256"]
            except Exception as error:
                item.update(status="input_unavailable", error=repr(error))
            output.append(item)
            print(member["inventory_label"], item["status"], item.get("error", ""), flush=True)
    finally:
        inputs.close()
    destination.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
