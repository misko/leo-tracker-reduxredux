"""Inventory or enqueue all saved native low-rate captures; never acquire RF."""

import argparse
import json
from pathlib import Path

from leo.application.partial_band import binding_for_capture
from leo.cli.adaptive_processing_queue import _catalog
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.partial_band import PartialBandStore


def backfill(*, captures, products, catalog=None, report=print):
    """Visit a fixed publication snapshot, retaining errors and every low-rate outcome.

    Historical admission intentionally ignores the live cadence's time cutoff.
    The catalog enforces source/configuration idempotence and worker capacity.
    """
    counts = dict(inspected=0, low_rate=0, ready=0, queued=0, existing_job=0, pending=0, errors=0)
    for _, session_id in captures.publication_index():
        counts["inspected"] += 1
        try:
            capture = captures.inspect(session_id)
            if capture.manifest.receipt.plan.geometry.sample_rate_hz != 1_250_000:
                continue
            counts["low_rate"] += 1
            binding = binding_for_capture(capture)
            status = products.status(session_id, capture.manifest_sha256)
            if status.state == "figures_ready":
                outcome = "ready"
            elif catalog is None:
                outcome = "pending"
            else:
                created = catalog.enqueue_adaptive_analysis_job(
                    session_id=session_id,
                    input_manifest_digest=capture.manifest_sha256,
                    configuration_digest=binding.digest,
                    priority=0,
                    resource_class="heavy",
                )
                outcome = "queued" if created else "existing_job"
            counts[outcome] += 1
            report(
                dict(
                    session_id=session_id,
                    outcome=outcome,
                    input_manifest_sha256=capture.manifest_sha256,
                    binding_sha256=binding.digest,
                    completed_visits=status.completed_visits,
                )
            )
        except (OSError, ValueError) as error:
            counts["errors"] += 1
            report(dict(session_id=session_id, outcome="error", error=str(error)))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--enqueue", action="store_true", help="Default is read-only inventory")
    args = parser.parse_args()
    captures = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        counts = backfill(
            captures=captures,
            products=PartialBandStore(args.bulk_root),
            catalog=_catalog() if args.enqueue else None,
            report=lambda row: print(json.dumps(row), flush=True),
        )
    finally:
        captures.close()
    print(json.dumps(dict(summary=counts)), flush=True)
    if counts["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
