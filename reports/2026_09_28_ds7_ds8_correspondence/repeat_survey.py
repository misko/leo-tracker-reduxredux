"""Catalogue-label persistent upper-edge tracks before selecting repeat excerpts."""

import json
import time
from pathlib import Path

from collect import OUT, label


def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    source = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    selected = json.loads((OUT / "selection.json").read_text())["selected"]
    started = time.monotonic()
    for row in selected:
        dest = OUT / (row["session_id"] + "-tracks.json")
        if dest.exists():
            continue
        labels = label(source.load(row["session_id"]), None, row["session_id"])
        dest.write_text(json.dumps(labels, indent=2) + "\n")
        print(row["session_id"], len(labels), flush=True)
        if time.monotonic() - started > 70:
            break
    source.close()


if __name__ == "__main__":
    main()
