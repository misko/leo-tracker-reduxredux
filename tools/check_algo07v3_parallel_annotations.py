"""External full-proposal comparison on explicit frozen recovery fixtures.

This fixture replay is not a standalone input path or a whole-scan benchmark.
Both implementations use owned context reconstruction; the older persisted
annotation remains an independent numerical oracle, never an inference input.
"""

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import algo07v3_serial_annotation_oracle as serial
import check_algo07v3_fixture_context as fixture_loader
import check_algo07v3_scan_likelihood as comparison
from check_algo07v3_fixture_context import owned_context
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v3.recovery_inventory import baseline_pair, inventory, select_targets
from leo.operations.localization_v3_job import source_bindings, stage_deadline
from leo.operations.localization_v3_parallel import map_predictive_folds


def require_exact(expected, actual):
    if expected != actual:
        raise ValueError("Complete annotation differs; do not compare only the winning identity")


def cpu_seconds():
    rows = [resource.getrusage(who) for who in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)]
    return sum(r.ru_utime + r.ru_stime for r in rows)


def run(args):
    if args.output.exists():
        raise ValueError("Fresh comparison receipt required")
    bindings, rows = {}, []

    def read(path):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if str(path) in bindings and bindings[str(path)] != digest:
            raise ValueError("Fixture changed during comparison: " + str(path))
        bindings[str(path)] = digest
        return json.loads(raw)

    modules = source_bindings()
    for receipt_path in args.fixture_receipt:
        receipt = read(receipt_path)
        source = Path(receipt["source"])
        reference_path = Path(receipt["output"]["path"])
        expected = read(reference_path)
        if bindings[str(reference_path)] != receipt["output"]["sha256"]:
            raise ValueError("Frozen annotation result changed")
        comparisons = []
        for side in ("serial", "parallel"):
            earlier = dict(bindings)
            context = owned_context(source, bindings)
            if any(bindings.get(path) != digest for path, digest in earlier.items()):
                raise ValueError("Reconstructed fixture changed between methods")
            pair, _ = baseline_pair(context)
            inv = inventory(
                context["scan"].tracks,
                read(source / "observations.json"),
                pair,
                identities=receipt["scan_identities"],
            )
            target = next(t for t in select_targets(inv)[0] if t["track_id"] == receipt["track_id"])
            began = time.monotonic()
            cpu_began = cpu_seconds()
            with stage_deadline(300):
                result = (serial.annotate if side == "serial" else annotate)(
                    context,
                    inv,
                    target["track_id"],
                    inactive_fragment=target["inactive_fragment"],
                    **({"map_folds": map_predictive_folds} if side == "parallel" else {}),
                )
            seconds = time.monotonic() - began
            cpu_elapsed = cpu_seconds() - cpu_began
            actual = fingerprint(result)
            require_exact(expected, actual)
            comparisons.append(
                dict(side=side, seconds=seconds, cpu_seconds=cpu_elapsed, exact=True)
            )
            print(json.dumps(dict(fixture=str(receipt_path), **comparisons[-1])), flush=True)
        rows.append(
            dict(
                fixture_receipt=str(receipt_path),
                track_id=receipt["track_id"],
                status=result["result"]["annotation"]["status"],
                fold_count=len(result["result"]["folds"]),
                proposal_count=sum(len(f["proposals"]) for f in result["result"]["folds"]),
                compared_fields=sorted(result),
                comparisons=comparisons,
            )
        )
    final_modules = source_bindings()
    if any(final_modules.get(name) != binding for name, binding in modules.items()):
        raise ValueError("Loaded numerical source bindings changed")
    modules = final_modules
    for path, digest in bindings.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError("Fixture changed: " + path)
    value = dict(
        exact_all_annotation_fields=True,
        rows=rows,
        inputs=bindings,
        modules=modules,
        tools={
            str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (__file__, serial.__file__, fixture_loader.__file__, comparison.__file__)
        },
        full_dataset_equivalence=False,
        whole_pipeline_speedup=None,
        scope="Frozen-context full annotations, including all losing proposals in both c arms",
    )
    with args.output.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-receipt", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
