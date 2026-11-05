"""Measure frozen worker context construction before numerical optimization.

External oracle only. It checks all read worker inputs against their exported
hashes and records the original helper's counter before either fit/audit begins.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory_path(stage, argv):
    if stage == "target-1-inclusion":
        return Path(argv[argv.index("--inventory") + 1])
    if stage != "target-1-audit":
        raise ValueError("Unknown numerical worker context")
    trial = Path(argv[argv.index("--trial") + 1])
    study = Path(argv[argv.index("--study") + 1])
    protocol = json.loads((trial / "protocol.json").read_bytes())
    for name in ("inactive_fragment_sources", "graph_bundle_sources", "measurement_refinements"):
        if protocol.get(name):
            raise ValueError("Additional context modifications need separate qualification")
    return study / "all-large-track-recovery" / protocol["job"]["job_id"] / "inventory.json"


def run(args):
    if args.output.exists():
        raise ValueError("Fresh context-count receipt required")
    folder = (args.evidence / "ALGO04").resolve()
    descriptor_path = folder / "descriptor.json"
    descriptor = json.loads(descriptor_path.read_bytes())
    worker = Path(descriptor["source_worker_root"])
    touched = set()

    def observe(event, values):
        if event == "open" and isinstance(values[0], (str, bytes)):
            p = Path(values[0].decode() if isinstance(values[0], bytes) else values[0]).resolve()
            if p.is_relative_to(worker):
                touched.add(p)

    sys.addaudithook(observe)
    sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
    import algo04_numerical_helper as helper
    from diagnose_all_large_tracks import context

    began = time.monotonic()
    rows, sources = {}, {}
    for stage in ("target-1-inclusion", "target-1-audit"):
        path = folder / "worker/recovery/numerical-receipts" / (stage + ".json")
        relative = str(path.relative_to(folder))
        if "sha256:" + sha(path) != descriptor["files"][relative]:
            raise ValueError("Original numerical receipt changed")
        original = json.loads(path.read_bytes())
        if sha(helper.__file__) != original["helper_sha256"]:
            raise ValueError("Different frozen numerical helper")
        if sha(original["script"]) != original["script_sha256"]:
            raise ValueError("Original numerical worker source changed")
        argv = original["arguments"]
        source_inventory = inventory_path(stage, argv)
        inventory = json.loads(source_inventory.read_bytes())
        if inventory["job"]["policy_kind"] != "baseline":
            raise ValueError("Other context preparation branches require separate qualification")
        with helper.patched_stages(reference_limit_s=30, centered_lbfgsb=True) as state:
            prepared = context(inventory)
        if state["optimizer_calls"] or state["reference_updates"]:
            raise ValueError("Context preparation unexpectedly performed numerical fitting")
        arms = sorted(prepared["problems"])
        if arms != ["c0", "fitted_c"] or state["problem_count"] != len(arms):
            raise ValueError("Unexpected original context construction count")
        rows[stage] = dict(
            receipt_sha256=sha(path),
            problem_count=state["problem_count"],
            arms=arms,
            optimizer_calls=state["optimizer_calls"],
            reference_updates=state["reference_updates"],
            helper_sha256=state["helper_sha256"],
            inventory_path=str(source_inventory),
            policy_kind=inventory["job"]["policy_kind"],
        )
        sources[str(path)] = sha(path)
    inputs = {}
    for path in sorted(touched):
        relative = str(Path("worker") / path.relative_to(worker))
        if not path.is_file() or relative not in descriptor["files"]:
            raise ValueError("Unbound original worker read: " + str(path))
        digest = sha(path)
        if "sha256:" + digest != descriptor["files"][relative] or sha(folder / relative) != digest:
            raise ValueError("Context input differs from the bound export")
        inputs[relative] = digest
    modules = {
        name: dict(path=m.__file__, sha256=sha(m.__file__))
        for name, m in sys.modules.items()
        if getattr(m, "__file__", None) and str(m.__file__).startswith(str(args.runtime))
    }
    result = dict(
        source=str(folder),
        input_sha256=descriptor["input_sha256"],
        stages=rows,
        inputs=inputs,
        numerical_receipts=sources,
        modules=modules,
        descriptor_sha256=sha(descriptor_path),
        tool=dict(path=__file__, sha256=sha(__file__)),
        seconds=time.monotonic() - began,
        scope="Two baseline-arm problems created by each original worker before fit/audit",
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(stages=rows, input_files=len(inputs), seconds=result["seconds"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("evidence", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
