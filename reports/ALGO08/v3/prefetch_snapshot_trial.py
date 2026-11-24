"""Compare measured normal and two-slot lookahead on the complete resident original."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[2]))
from reports.ALGO08.v3 import original_full_detector_boundary as full
from reports.ALGO08.v3.prefetch_snapshot_accounting import PrefetchAccounting

ORDER = ("fresh-1", "reuse-1", "reuse-2", "fresh-2")


def worker(output, book, reuse):
    import empty_bootstrap as boot

    observation = PrefetchAccounting(reuse)
    load = boot.load_runtime

    def measured():
        runtime = load()
        import combined_frontier_run as frontier

        stack.enter_context(observation.binding(frontier))
        return runtime

    from contextlib import ExitStack

    with ExitStack() as stack:
        stack.enter_context(patch.object(boot, "load_runtime", measured))
        full.worker(output, book)
    (output / "snapshot-accounting.json").write_text(json.dumps(observation.result(), sort_keys=True) + "\n")


def local_residency(book):
    from visit_frame_raw_0016 import resident

    paths = full.enrolled_paths(book)
    cache = resident(paths)
    if cache["members"] != len(paths):
        raise RuntimeError("Require complete existing residency, with no warming")
    return cache


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE
    from short_raw_diagnostic import measure

    source = Path(__file__).resolve()
    layers = (source, source.with_name("prefetch_snapshot_accounting.py"))
    book = full.admission() | dict(machine=host(), sources={path.name: sha256(path.read_bytes()).hexdigest()
                                                            for path in layers})
    local_residency(book)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    path = root / "binding.json"
    write(path, book)
    binding_pin = sha256(path.read_bytes()).hexdigest()
    write(root / "order.json", dict(order=ORDER, binding_sha256=binding_pin))
    for arm in ORDER:
        output = root / arm
        before = local_residency(book)
        command = [str(RELEASE / "venv/bin/python"), "-IB", str(source), "worker", str(output),
                   "--binding", str(path), "--binding-pin", binding_pin, "--arm", arm]
        result = measure(command, environment_for(root), output)
        write(root / f"clock-{arm}.json", dict(clock=result, command=command, before=before,
                                             after=local_residency(book)))
        if result["exit_code"]:
            raise RuntimeError(result["stderr_tail"])


def score(root):
    from aperture_trial import write

    def read(path):
        return json.loads((root / path).read_bytes())

    order = read("order.json")
    book = json.loads(full.pinned(root / "binding.json", order["binding_sha256"]))
    if tuple(order["order"]) != ORDER:
        raise ValueError("Expected the frozen opposite orders")
    request = book["request"]
    expected = full.pinned(Path(book["reference_native"]), request["native"])
    fields = ("manifest_sha256", "chunk_index", "encoded", "decoded", "windows",
              "member_sha256", "index_sha256", "raw_sha256")
    roster = [tuple(row[key] for key in fields) for row in book["roster"]]
    arms = {}
    for arm in ORDER:
        output = root / arm
        measured = read(f"clock-{arm}.json")
        clock = measured["clock"]
        path = output / "detections.json"
        live = read(f"{arm}/worker.json")
        accounting = read(f"{arm}/snapshot-accounting.json")
        worker = accounting["members"]
        stats = accounting["prefetch"]
        inventory = live["source"]["members"]
        if (full.pinned(path, request["native"]) != expected or clock["exit_code"]
                or [tuple(row[k] for k in fields) for row in inventory] != roster
                or live["source"]["finished_raw_authority"] != request["authority"]
                or live["selection"]["choice"]["route"] != "unfiltered"
                or live["receiver"]["issued"] != full.WINDOWS or sum(row["encoded"] for row in inventory) != full.COMPRESSED
                or len(worker) != stats["hits"] or stats["hits"] != full.MEMBERS - 2 or stats["fallback"]
                or sum(r["cpu_ns"] for r in worker) != stats["worker_cpu_ns"]
                or sum(r["bytes"] for r in worker) != stats["hit_bytes"]
                or any(not r["supplied"] or r["input_blocks"] for r in worker)
                or any(r["complete_encoded_auth"]["input_blocks"] for r in inventory)):
            raise ValueError(f"The {arm} child changed source, coverage or native publication")
        calls = [call for row in worker for call in row["calls"]]
        metrics = ("cpu_ns", "wall_ns", "user_ns", "system_ns", "minor_faults", "major_faults", "input_blocks")
        categories = {key: dict(calls=sum(r["operation"] == key for r in calls), **{
            metric: sum(r[metric] for r in calls if r["operation"] == key) for metric in metrics
        }) for key in ("allocate", "readv", "descriptor_fstat", "eof_read")}
        if sum(r["bytes"] for r in calls if r["operation"] == "readv") != stats["hit_bytes"]:
            raise ValueError("The syscall trace must include every prefetched byte")
        slots = accounting["slots"]
        if not (sum(row.get("reuses", 0) for row in slots) > 0) == arm.startswith("reuse"):
            raise ValueError("Expected private lease reuse only in the enabled arms")
        arms[arm] = dict(process=measured, receiver=live["receiver"]["acquire"],
                         detector=full.boundaries(clock, live, path.stat().st_mtime_ns),
                         prefetch=accounting, leaf_cost=categories,
                         worker_cpu_other_ns=stats["worker_cpu_ns"] - sum(r["cpu_ns"] for r in calls),
                         main_encoded_cpu_ns=sum(r["complete_encoded_auth"]["cpu_ns"] for r in inventory))
    write(root / "result.json", dict(qualified=True, case=full.CASE, order=ORDER, bytes=full.COMPRESSED,
        members=full.MEMBERS, windows=full.WINDOWS, binding_sha256=order["binding_sha256"],
        source_pins=book["sources"], request=request, arms=arms, solver_children=0, backing_waveform_bytes=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--binding-pin")
    cli.add_argument("--arm", choices=ORDER)
    values = cli.parse_args()
    if values.action == "launch":
        launch(values.root)
    elif values.action == "score":
        score(values.root)
    else:
        worker(values.root, json.loads(full.pinned(values.binding, values.binding_pin)), values.arm.startswith("reuse"))
