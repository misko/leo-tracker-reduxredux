"""External original/owned 72-hour causal catalogue preparation comparison."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    started = time.monotonic()
    if args.side == "reference":
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        import algo06_prepare

        algo06_prepare.write = lambda *a: None
    from leo.operations.tle_archive import TleArchiveReader

    if args.side == "candidate":
        from check_algo07v3_track_preparation import deny_legacy

        from leo.operations.localization_v3_inputs import prepare_recovery_catalogue

        # This is an owned operational adapter test. Import that adapter before
        # the numerical-only guard; all subsequent legacy access remains banned.
        sys.addaudithook(deny_legacy)
    archive = TleArchiveReader(args.archive)
    inputs = {}

    class BoundReader:
        def list_snapshots(self, provider):
            return archive.list_snapshots(provider)

        def read(self, snapshot):
            text = archive.read(snapshot)
            inputs[str(snapshot.path)] = snapshot.sha256
            return text

    if args.side == "reference":
        result = algo06_prepare.export_catalogue(
            args.output.parent, args.cutoff, reader=BoundReader()
        )
    else:
        result = prepare_recovery_catalogue(BoundReader(), args.cutoff)
    args.output.write_text(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=digest(path))

    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - started,
        cutoff=args.cutoff,
        inputs=inputs,
        output=binding(args.output),
        tool=binding(__file__),
        scope="72-hour causal catalogue preparation through read-only archive port",
        full_pipeline_parity=False,
        modules={
            name: binding(m.__file__)
            for name, m in sys.modules.items()
            if getattr(m, "__file__", None)
            and (
                str(m.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(m.__file__)
                or name == "check_algo07v3_track_preparation"
            )
        },
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                elements=len(result["elements"]),
                seconds=receipt["seconds"],
                output=receipt["output"],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    for name in ("runtime", "archive", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cutoff", type=int, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Catalogue output exists")
    run(args)
