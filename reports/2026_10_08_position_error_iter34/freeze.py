"""Freeze candidate-pair construction and control before reading pair statistics."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    path = HERE / "protocol.json"
    if path.exists():
        raise FileExistsError("Immutable pair audit")
    parent = json.loads((REPORTS / "2026_10_08_position_error_iter33/protocol.json").read_text())
    sources = parent["source_sha256"]
    for f, digest in sources.items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    paths = list(HERE.glob("*.py"))
    paths.extend(
        REPORTS / "2026_10_08_position_error_iter33/results" / f"{label}.json"
        for label in parent["cases"]
    )
    for item in paths:
        sources[str(item.relative_to(REPORTS))] = hashlib.sha256(item.read_bytes()).hexdigest()
    plan = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        labels=list(parent["cases"]),
        sigmas_s=[2, 0.75],
        scope="Candidate-pair audit; no identities assumed, fits or new constraints",
        pairing="Same rounded millisecond and exactly equal RF; exactly one row per receiver",
        exclusions="Report unmatched/multiple-row groups; inference data unchanged",
        seed=2026100834,
        control="For each pair choose a singleton RX1 at same RF, at least30s apart, uniformly",
        comparison="Compare coincident/null on identical RX0 groups; keep all-pair stats too",
        residual="Circular RX1-RX0 after each saved model's receiver/RF nuisance correction",
        thresholds_hz=[125, 250, 500],
        limitations="Coincidence is not identity; null groups are not independent trials",
        source_sha256=sources,
    )
    path.write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen", len(sources), "hashes")


if __name__ == "__main__":
    main()
