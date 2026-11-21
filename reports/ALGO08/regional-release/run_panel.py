"""Run as the inference user; read only opaque inputs, lock predictions before scoring."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def evaluate(public, output, assets):
    panel = json.loads((public / "panel.json").read_bytes())
    def worker(job):
        region = public / (job["offer"] + ".json")
        receipt = json.loads(subprocess.check_output([sys.executable, "-Bs", "-m", "tools.algo08_scan",
            "--recording", str(public / job["recording"]), "--region", str(region),
            "--assets", str(assets), "--archive", str(public / "tle"), "--bulk-root", str(output)],
            text=True))
        rid = receipt["run_id"]
        store = FastStandardAnalysisStore(output)
        detail = store.detail(rid)
        terminal = json.loads((FastScanStore(output).automatic_workspace(rid)/"terminal.json").read_bytes())
        assert detail["region"] == terminal["region"]
        assert detail["region"]["center"] == json.loads(region.read_bytes())["center"]
        if detail["state"] == "complete":
            assert detail["evaluation_reference"] is None and len(detail["artifacts"]) == 8
            for name in ("position_grid", "position_path"):
                evidence = getattr(store, name)(rid)
                assert evidence["region_center"] == detail["region"]["center"]
                assert evidence["box_width_km"] == detail["region"]["width_km"]
            for entry in detail["artifacts"]:
                Image.open(BytesIO(store.artifact(rid, entry["name"], entry["sha256"]))).verify()
        else:
            assert detail["state"] == "withheld" and not detail["artifacts"]
        return {**job, **receipt, "region": detail["region"], "arms": terminal["arms"],
                "reason": terminal["reason"], "png_count": len(detail["artifacts"])}
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(worker, panel["jobs"]))
    assert len(set(r["run_id"] for r in rows)) == len(rows)
    immutable_json(output / "predictions.json", dict(commitment=panel["commitment"], rows=rows))
    return hashlib.sha256((output / "predictions.json").read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("public", "output", "assets"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(evaluate(args.public, args.output, args.assets))
