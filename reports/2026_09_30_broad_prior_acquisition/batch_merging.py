"""At most eight independent merger replays, with explicit bounded concurrency."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import time

from common import HERE, selected_units, write_new, digest
from launch import launch


def run_batch(number, workers):
    if not 1 <= number <= 8 or workers not in (1, 2):
        raise ValueError("batch 1..8 and workers 1..2 required")
    units = selected_units()[(number-1)*8:number*8]
    output = HERE / "runs" / "merging" / f"batch-{number:02}"
    if (output / "batch.json").exists():
        raise FileExistsError("preserve existing batch")
    started = time.monotonic()
    def one(unit):
        existing = output / (unit + "-merge128_to32.launch.json")
        if existing.exists():
            return json.loads(existing.read_text())
        if time.monotonic()-started > 809:
            return {"unit_id":unit, "status":"not_started_batch_budget"}
        return launch(unit,output)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [f.result() for f in as_completed([pool.submit(one,u) for u in units])]
    summary = []
    for row in rows:
        native = json.loads(Path(row["prediction_path"]).read_text()) if row.get("native_prediction_exists") else {}
        summary.append({"unit_id":row["unit_id"], "launcher_status":row["status"],
            "status":native.get("status",row["status"]), "factors":len(native.get("checkpoints",[])),
            "gate_failures":native.get("gate_failures",[]), "exception":native.get("exception"),
            "seconds":row.get("wall_seconds")})
    receipt = {"batch":number,"workers":workers,"units":units,"rows":summary,
        "wall_seconds":time.monotonic()-started,"protocol_sha256":digest(HERE/"PROTOCOL.md")}
    write_new(output / "batch.json",receipt)
    print(json.dumps(receipt),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("number",type=int)
    parser.add_argument("--workers",type=int,default=1)
    args = parser.parse_args()
    run_batch(args.number,args.workers)
