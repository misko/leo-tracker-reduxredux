"""External exact oracle for frozen-competition annotation numerical replay."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from algo07v3_inclusion_oracle import original_callable
from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    bindings = {}

    def read(path):
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    began = time.monotonic()
    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.annotation_replay import replay_annotation

        context = owned_context(args.source, bindings)
        result = replay_annotation(
            context,
            read(args.inventory),
            dict(
                result=read(args.annotation / "result.json"),
                protocol=read(args.annotation / "protocol.json"),
            ),
        )
    else:
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import algo04_annotation_replay as original
        from benchmark_graph_covariance import load_case

        context = load_case(args.source.parent, args.source.name)
        captured = {}
        original_callable(
            original.replay_annotation,
            read=read,
            context=lambda _: context,
            write=lambda path, value: captured.update({path.name: value}),
        )(args.inventory, args.annotation, Path("/explicit-numerical-annotation"))
        result = dict(protocol=captured["protocol.json"], result=captured["result.json"])
    # Only external file provenance and measured elapsed time are normalized.
    # Frozen scientific source metadata is otherwise retained on both sides.
    result["result"].pop("seconds", None)
    for row in (result["protocol"], result["result"]):
        row["numerical_replay"].pop("source", None)
        row["numerical_replay"].pop("source_sha256", None)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    # Bind all frozen scientific inputs read through the reference context loader.
    for directory in (args.source, args.source.parent / "causal_prior" / args.source.name):
        for path in directory.iterdir():
            if path.is_file():
                bindings[str(path)] = binding(path)["sha256"]
    cavity = args.source.parent / "family_cavity/position" / f"{args.source.name}.json"
    bindings[str(cavity)] = binding(cavity)["sha256"]
    modules = {
        n: binding(m.__file__)
        for n, m in sys.modules.items()
        if getattr(m, "__file__", None)
        and (
            str(m.__file__).startswith(str(args.runtime))
            or "/src/leo/" in str(m.__file__)
            or n
            in (
                    "check_algo07v3_fixture_context",
                "algo07v3_inclusion_oracle",
                "check_algo07v3_scan_likelihood",
                "check_algo07v3_track_preparation",
            )
        )
    }
    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - began,
        inputs=bindings,
        modules=modules,
        tool=binding(__file__),
        output=binding(args.output),
        scope="Frozen-context annotation numerical replay only",
        full_pipeline_parity=False,
    )
    args.output.with_suffix(".receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({k: receipt[k] for k in ("seconds", "scope", "output")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "inventory", "annotation", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    run(parser.parse_args())
