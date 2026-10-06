"""Bounded, resumable native 1.25 MS/s GLRT replay; never acquires RF."""

import argparse
import json
import os
from pathlib import Path

from leo.application.partial_band import replay_partial_band
from leo.cli.partial_band_position import publish_partial_band_positions
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.partial_band import PartialBandStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--maximum-seconds", type=float, default=560.0)
    parser.add_argument("--maximum-visits", type=int, default=3000)
    parser.add_argument("--maximum-workers", type=int, choices=(1,), default=1)
    args = parser.parse_args()
    os.nice(10)
    captures = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    products = PartialBandStore(args.output_root or args.bulk_root, read_only=False)
    try:
        result = replay_partial_band(
            captures=captures,
            products=products,
            session_id=args.session_id,
            maximum_seconds=args.maximum_seconds,
            maximum_visits=args.maximum_visits,
            maximum_workers=args.maximum_workers,
            progress=lambda p: print(json.dumps({"progress": p}), flush=True),
        )
        if result.get("state") == "figures_ready":
            capture = captures.inspect(args.session_id)
            status = products.status(args.session_id, capture.manifest_sha256)
            if status.manifest is None:
                raise ValueError("partial-band figures lack a verified manifest")
            publish_partial_band_positions(args.output_root or args.bulk_root, status.manifest)
    except BlockingIOError:
        result = dict(state="busy", session_id=args.session_id)
    finally:
        captures.close()
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
