"""Replay the installed paired ALGO08 solver with and without canonical Graph proposals."""

import argparse
import gzip
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import process_time
from unittest.mock import patch

from leo.application import localization_v3
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.qualification.paired_publication import archive_identity
from tools.pipeline_eval.variants.experimental.graph_alias import canonical_alias_proposals

from graph_saved_trial import digest


def replay(document, archive, assets, offer, canonical):
    metrics = Counter()
    ordinary_prepare = localization_v3.prepare_tracks

    def prepare(*args, **kwargs):
        with canonical_alias_proposals() as changes:
            result = ordinary_prepare(*args, **kwargs)
        metrics.update(changes)
        return result

    start = process_time()
    with patch.object(localization_v3, "prepare_tracks", prepare if canonical else ordinary_prepare):
        decision, packet, policy = algo08_position.solve(
            document, TleArchiveReader(archive), assets, offer,
        )
    cpu = process_time() - start
    arms = decision["arms"]
    evidence = {}
    if packet is not None:
        arms = {
            arm: dict(values, **{
                name: packet["arms"][arm][name] for name in (
                    "associated_points", "owner_sha256", "satellites",
                )
            })
            for arm, values in arms.items()
        }
        grid = packet["position_grid"]
        evidence = {field: digest(packet[field]) for field in ("position_path", "objective_replay")}
        evidence.update(
            position_grid=digest({key: value for key, value in grid.items()
                                  if key not in ("binding", "elapsed_seconds")}),
            grid_evaluated_points=grid["evaluated_points"], grid_complete=grid["complete"],
        )
    return dict(status=decision["status"], reason=decision.get("reason"), arms=arms,
                orbit_policy=policy, cpu_s=cpu, graph_changes=dict(metrics), evidence=evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("expected_native")
    parser.add_argument("assets", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("expected_archive")
    parser.add_argument("mirrored_offers", type=Path)
    parser.add_argument("site", choices=("north", "south"))
    parser.add_argument("--canonical-only", action="store_true")
    args = parser.parse_args()

    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.expected_native:
        raise ValueError("The saved detection bytes differ from the replay pin")
    archive = archive_identity(args.archive)
    if archive["snapshots_sha256"] != args.expected_archive:
        raise ValueError("The capture-time archive differs from the replay pin")
    with gzip.open(args.mirrored_offers, "rt") as stream:
        offers = json.load(stream)["sites"][args.site]
    document = json.loads(raw)
    results = {}
    for name, order in (("inside", (False, True)), ("outside", (True, False))):
        offer = Algo08Region.parse(offers[name]["offer"])
        results[name] = dict(region=offer.document(), runs={})
        for canonical in (True,) if args.canonical_only else order:
            mode = "canonical" if canonical else "reference"
            results[name]["runs"][mode] = replay(document, args.archive, args.assets, offer, canonical)
    if archive_identity(args.archive) != archive:
        raise ValueError("The capture-time archive changed during replay")
    print(json.dumps(dict(
        native_sha256=args.expected_native, archive=archive, cases=results,
        offered_regions_sha256=sha256(args.mirrored_offers.read_bytes()).hexdigest(),
    ), default=_json_value, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
