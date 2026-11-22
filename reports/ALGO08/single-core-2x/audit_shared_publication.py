"""Verify two full publications against each other from their actual local files."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def audit(pair):
    data = json.loads(pair.read_bytes())
    if "failure" in data:
        raise ValueError("Cannot audit a failed pair as an exact success")
    before, after = (data["runs"][method] for method in ("baseline", "candidate"))
    for key in ("arms", "owners", "scientific_digests", "artifacts"):
        if before[key] != after[key]:
            raise ValueError(f"Different published {key}")
    probes, figures = {}, {}
    for method, row in data["runs"].items():
        root = pair.parent / method
        files = list((root / "fast-scan-automatic-work").glob("*/detections.json"))
        if len(files) != 1:
            raise ValueError("Expected one sealed receiver output")
        doc = json.loads(files[0].read_bytes())
        probes[method] = doc["source"]["probes"]
        store = FastStandardAnalysisStore(root)
        for item in row["artifacts"]:
            image = store.artifact(row["receipt"]["run_id"], item["name"], item["sha256"])
            with Image.open(BytesIO(image)) as decoded:
                if decoded.format != "PNG":
                    raise ValueError("Wrong figure format")
                decoded.load()
                figures[item["name"]] = list(decoded.size)
    if probes["baseline"] != probes["candidate"] or len(figures) != 8:
        raise ValueError("Receiver or figure coverage changed")
    packed = json.dumps(probes["baseline"], sort_keys=True, separators=(",", ":")).encode()
    return dict(session=before["receipt"]["session_id"], probe_rows=len(probes["baseline"]),
                selected=sum(len(r["candidates"]) for r in probes["baseline"]),
                probe_rows_sha256=sha256(packed).hexdigest(), image_dimensions=figures,
                elapsed_speedup=before["elapsed_s"]/after["elapsed_s"],
                cpu_speedup=before["cpu_s"]/after["cpu_s"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({p.parent.name: audit(p) for p in args.pair}, indent=2))
