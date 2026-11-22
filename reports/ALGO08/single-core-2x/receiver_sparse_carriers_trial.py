"""Compare a sparse eligible-bin sweep against the frozen spectral receiver."""

import argparse
import json
from pathlib import Path

from . import receiver_cfo_native_trial as native
from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import exports, run
from .receiver_frame_planes_composed import check_regression
from .receiver_spectral_vectors_check import CANDIDATE_SHA as REFERENCE_SHA
from .receiver_spectral_vectors_trial import compile_variants, measure
from tools.pipeline_eval.variants.experimental import receiver_sparse_carriers


STOCK_SOURCE = "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a"
STOCK_OBJECT = "5ffc8eb34785b7d20535549da23ba521cf954f86b6cfabce96c0c71ac664292d"


def build(work, bench, assets):
    work.mkdir()
    actual = bench / "integration-spectral-vectors-terminal-veto/receiver.so"
    archive = json.loads((bench / "spectral-vectors-combined-v1.json").read_bytes())["build"]
    parent = json.loads((bench / "d97b-planes-and-fir/build.json").read_bytes())
    restore.digest(actual, REFERENCE_SHA)
    previous = archive["builds"]["packed"]
    if previous["library_sha256"] != REFERENCE_SHA:
        raise ValueError("Native receipt is for a different spectral receiver")
    original_link = previous["commands"][-1]
    timing = next(Path(item) for item in original_link if Path(item).name == "timing_first_receiver.o")
    source = timing.with_suffix(".c")
    restore.digest(source, STOCK_SOURCE)
    for item in original_link:
        if item.endswith(".o"):
            path = Path(item)
            expected = STOCK_OBJECT if path == timing else parent["objects"][path.name]
            restore.digest(path, expected)
    reference = work / "reference.so"
    run([*original_link[:-1], reference], cwd=restore.PINNED)
    restore.digest(reference, REFERENCE_SHA)
    # A new PGO arm supplies its own feedback flags. Keep every other linker input.
    link = [original_link[0], *original_link[original_link.index("-shared"):]]
    stock = source.read_text()
    vector = receiver_sparse_carriers.overlay(stock)
    profile, builds = compile_variants(work, link, timing, stock, vector, assets)
    if exports(work / "packed/use.so") != exports(reference):
        raise ValueError("The sparse sweep changed the public receiver symbols")
    return dict(
        reference_sha256=REFERENCE_SHA, profile_command=profile, builds=builds,
        sources={name: restore.digest(restore.HERE / name) for name in (
            "receiver_sparse_carriers.inc", "receiver_sparse_carriers.py",
        )},
    )


def trial(work, bench, assets, weak, archive, source_audit, wide_reference):
    receipt = build(work, bench, assets)
    groups = native.inputs(weak, archive, source_audit, wide_reference)
    return dict(
        build=receipt,
        native=measure(dict(reference=work / "reference.so", packed=work / "packed/use.so"), groups, assets),
        stages=measure(dict(reference=work / "profile-reference/use.so",
                            packed=work / "profile-packed/use.so"),
                       {"ds26-weak": groups["ds26-weak"]}, assets, profile=True),
    )


def regression(work, receipt, bench, assets, pair, candidate, binding, bulk):
    identity = json.loads(receipt.read_bytes())["build"]
    return check_regression(work / "packed/use.so", identity["builds"]["packed"]["library_sha256"],
                            bench, assets, pair, candidate, binding, bulk)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (trial, ("work", "bench", "assets", "weak", "archive", "source_audit", "wide_reference")),
        (regression, ("work", "receipt", "bench", "assets", "pair", "candidate", "binding", "bulk")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for field in fields:
            command.add_argument(field, type=lambda value: Path(value).resolve())
    args = vars(parser.parse_args())
    handler = args.pop("handler")
    args.pop("action")
    print(json.dumps(handler(**args), indent=2, allow_nan=False))
