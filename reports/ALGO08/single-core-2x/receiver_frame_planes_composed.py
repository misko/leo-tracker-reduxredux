"""Link the frozen frame planes and FIR tile and check their combined receiver."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np

from . import receiver_cfo_lineage_trial as lineage
from . import receiver_cfo_native_trial as native
from . import receiver_cfo_restore_object as restore
from .receiver_cfo_wrap_build import FULL_RESTORATION_SHA, exports, run
from .receiver_fir_tile_trial import WRAPPED_SHA
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest


PLANES = {
    "use.so": "7c8133ae26ba231e7ee7da4af4554522ea5b18705c89f9a5333902a39eb15cfc",
    "timing_first_receiver.o": "2fa7e2bb668f685198b789388343b6e28a5dfbf0823c946c674b473cec26f8e8",
    "timing_first_receiver.c": "2107d88f8fa827c00133844d74c6f1766aa782bd70781c36c76aa7ff591e0c5c",
}
FIR = {
    "tile.so": "cb57aa1e83463ccb7fe491115f961bb21f565736838eee110d7b398a974f1898",
    "delay_pgo.o": "d4af8c66bc99b2aa3eacf4f7ec6e59e8d84dd782a195e0d5494034b5177f37e5",
    "tile.o": "a106c015af3173c21e7313d0b49693c3dd59097c0a02a5dbc03a444667305ea2",
}
SOURCES = {
    "receiver_frame_planes.inc": "806918aa6570d7a93c7ecae8612e737c4f9104a19479580fe71d3a3165feae63",
    "receiver_frame_planes.py": "ae6e92da3e59ebdb8c54296916f63ce9d10fcd69e8ed082c4bc3943180c11360",
    "receiver_fir_tile.c": "a45f25bee6ceffe35258f2e10f2d5af009b577bd064016fcc4a2db5c409058ab",
}


def compose(work, bench, assets, weak, archive, source_audit, wide_reference):
    planes, tiled = (bench / label for label in ("d97b-frame-planes-v2", "d97b-fir-tile-v1"))
    for root, identities in ((planes, PLANES), (tiled, FIR), (restore.HERE, SOURCES)):
        for name, expected in identities.items():
            restore.digest(root / name, expected)
    work.mkdir()
    fir_manifest = json.loads((bench / "d97b-fir-tile-v1.json").read_bytes())["build"]
    link = fir_manifest["commands"][-1]
    wrapped = bench / "receiver-cfo-wrap-fix/wrapped.so"
    restore.digest(wrapped, WRAPPED_SHA)
    rebuilt = work / "tile-reference.so"
    run([*link[:-1], rebuilt], cwd=restore.PINNED)
    restore.digest(rebuilt, FIR["tile.so"])
    index, = [i for i, part in enumerate(link) if Path(part).name == "timing_first_receiver.o"]
    link[index] = str(planes / "timing_first_receiver.o")
    combined = work / "receiver.so"
    command = run([*link[:-1], combined], cwd=restore.PINNED)
    if exports(combined) != exports(wrapped):
        raise ValueError("The composed receiver changed the wrapped receiver ABI")
    identity = dict(
        reference_sha256=WRAPPED_SHA, candidate_sha256=restore.digest(combined),
        frame_planes=PLANES, tiled_fir=FIR, sources=SOURCES, link=command,
        objects={Path(item).name: restore.digest(Path(item)) for item in command if item.endswith(".o")},
    )
    groups = native.inputs(weak, archive, source_audit, wide_reference)
    with ExitStack() as stack:
        radios = {}
        for edge in ("lower", "upper"):
            asset = assets / f"{edge}.f32"
            restore.digest(asset, PINS[asset.name])
            template = np.fromfile(asset, dtype="<f4")
            for arm, path in (("wrapped", wrapped), ("combined", combined)):
                radio = Receiver(path, template)
                stack.callback(radio.close)
                radios[edge, arm] = radio
        comparisons = (("wrapped", "combined"),)
        batches = {label: native.measure(rows, radios, ("wrapped", "combined"), comparisons, cycles=6)
                   for label, rows in groups.items()}
    for label, batch in batches.items():
        counts = batch["paired"]["wrapped_to_combined"]["counts"]
        if counts["lanes_changed"] or counts["continuation_changed"]:
            raise ValueError(f"The composed build diverged on {label}")
    (work / "build.json").write_text(json.dumps(identity, indent=2) + "\n")
    return dict(build=identity, measured=batches)


def regression(work, bench, assets, pair, candidate, binding, bulk):
    archived = json.loads((bench / "receiver-cfo-lineage-restoration.json").read_bytes())
    archived = {row["visit"]: row for row in archived["rows"]}
    batch = json.loads(pair.read_bytes())
    rows = lineage.saved_rows(candidate, "candidate", batch)
    saved = lineage.load_samples(binding, bulk, batch, rows)
    combined = work / "receiver.so"
    restored = bench / "receiver-cfo-lineage-fix/restored.so"
    identity = json.loads((work / "build.json").read_bytes())
    restore.digest(combined, identity["candidate_sha256"])
    restore.digest(restored, FULL_RESTORATION_SHA)
    asset = np.frombuffer(lineage.pin(assets / "lower.f32", PINS["lower.f32"]), dtype="<f4")
    outcomes = []
    with ExitStack() as stack:
        radios = [Receiver(path, asset) for path in (restored, combined)]
        for radio in radios:
            stack.callback(radio.close)
        for visit, window in saved.items():
            if window["iq_sha256"] != archived[visit]["iq_sha256"]:
                raise ValueError(f"The prior regression I/Q differs for visit {visit}")
            old, new = (radio.timed(window["samples"], window["lane"], window["center"])[0]
                        for radio in radios)
            expected, = (entry["all_factors"] for entry in archived[visit]["builds"]
                         if entry["build"] == "restored-delay-product")
            digests = [digest(native.factor_bytes(items)) for items in (expected, old, new)]
            if len(set(digests)) != 1:
                raise ValueError(f"The restored regression factors differ for visit {visit}: {old} / {new}")
            outcomes.append(dict(visit=visit, iq_sha256=window["iq_sha256"], lane=window["lane"],
                                 channel=window["channel"], factors=new, factor_sha256=digests[0]))
    return dict(candidate_sha256=identity["candidate_sha256"], restored_sha256=FULL_RESTORATION_SHA,
                rows=outcomes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for handler, fields in (
        (compose, ("work", "bench", "assets", "weak", "archive", "source_audit", "wide_reference")),
        (regression, ("work", "bench", "assets", "pair", "candidate", "binding", "bulk")),
    ):
        command = commands.add_parser(handler.__name__)
        command.set_defaults(handler=handler)
        for name in fields:
            command.add_argument(name, type=lambda value: Path(value).resolve())
    arguments = vars(parser.parse_args())
    handler = arguments.pop("handler")
    arguments.pop("action")
    print(json.dumps(handler(**arguments), allow_nan=False, indent=2))
