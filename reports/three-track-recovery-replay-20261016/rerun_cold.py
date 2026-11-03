"""Rebuild a declared cold training fold and optionally rerun bounded discovery."""
import argparse
import hashlib
import json
from pathlib import Path

import replay
from leo.cli import shared_fast_position as pipeline
from leo.application import shared_fast_position as application
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.operations.tle_archive import TleArchiveReader


def prepare(args):
    folder = replay.HERE / "checkpoints" / args.fold
    derivation = replay.verified_json(folder / "derivation.json")
    terminal = replay.verified_json(folder / "terminal.json")
    document = replay.verified_json(args.input, derivation["parent_input_sha256"])
    source = pipeline.load_input(document)
    winners = {}
    for point in project_scanner_candidates(source):
        previous = winners.get(point.source_group_id)
        key = lambda p: (-p.margin, p.candidate_rank, p.candidate_id)
        if previous is None or key(point) < key(previous):
            winners[point.source_group_id] = point
    points = sorted(winners.values(), key=lambda p: (p.support_center_utc_ns, p.source_group_id))
    if len(points) != derivation["original_observations"]:
        raise ValueError("Original observation ordering differs")
    keys = {(points[i].visit_index, points[i].receiver_id, points[i].probe_index)
            for i in derivation["withheld_original_rows"]}
    derived = {k: v for k, v in document.items() if k in
               ("source", "clock_anchor", "delivery_clocks", "last_sample_counter")}
    probes = derived["source"]["probes"]
    derived["source"]["probes"] = [p for p in probes if
        (p["visit_index"], p["receiver_id"], p["probe_index"]) not in keys]
    if len(probes) - len(derived["source"]["probes"]) != derivation["withheld_count"]:
        raise ValueError("Withheld probe removal differs")
    payload = (json.dumps(derived, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if hashlib.sha256(payload).hexdigest() != derivation["derived_input_sha256"]:
        raise ValueError("Derived training-input digest differs")
    snapshot = next(s for s in TleArchiveReader(args.tle_root).list_snapshots()
                    if s.digest == terminal["provenance"]["tle_sha256"])
    TleArchiveReader(args.tle_root).read(snapshot)  # Check archive bytes before creating an attempt.
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "training-input.json").write_bytes(payload)
    (args.output / "derivation.json").write_text(json.dumps(derivation, indent=2) + "\n")
    receipt = dict(fold=args.fold, parent_input_sha256=derivation["parent_input_sha256"],
        derived_input_sha256=derivation["derived_input_sha256"],
        withheld_probe_groups=len(keys), tle_sha256=snapshot.digest,
        maximum_seconds=480, run_requested=args.run,
        discovery_priority_view=getattr(args, "priority_view", "all"),
        scope="Existing exported observations only; no recording or production publication. Pinned archived TLE selection overrides only this research process.")
    (args.output / "preparation-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return snapshot, receipt


def main(args):
    # Check all capsule sources/checkpoints before trusting recorded row definitions.
    replay.verify_capsule()
    snapshot, receipt = prepare(args)
    print(json.dumps(receipt), flush=True)
    if not args.run:
        return

    class PinnedArchive(TleArchiveReader):
        def select_latest_before(self, cutoff_utc_ns, provider=None):
            if snapshot.collected_utc_ns >= cutoff_utc_ns:
                raise ValueError("Pinned TLE snapshot is not strictly causal")
            if provider is not None and snapshot.provider != provider:
                raise ValueError("Pinned TLE provider differs")
            return snapshot

    previous = pipeline.TleArchiveReader
    previous_discovery = application.discover_channel_groups
    def prioritized_discovery(*discovery_args, **kwargs):
        return previous_discovery(*discovery_args, **dict(kwargs,
            priority_view=getattr(args, "priority_view", "all")))
    pipeline.TleArchiveReader = PinnedArchive
    application.discover_channel_groups = prioritized_discovery
    try:
        result = pipeline.run(args.output / "training-input.json", args.output / "output",
                              maximum_seconds=480, tle_root=args.tle_root)
    finally:
        pipeline.TleArchiveReader = previous
        application.discover_channel_groups = previous_discovery
    print(json.dumps({k: result.get(k) for k in ("state", "reason", "elapsed_seconds", "selection")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--tle-root", required=True, type=Path)
    parser.add_argument("--fold", required=True, choices=("early_to_late", "late_to_early"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="Run fresh discovery, bounded to 480 seconds")
    parser.add_argument("--priority-view", choices=("all", "low", "high"), default="all",
                        help="Training view that prioritizes adaptive spatial refinement")
    main(parser.parse_args())
