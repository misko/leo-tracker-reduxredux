"""Freeze an initial-joint-fit prior sweep before observing refitted outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    path = HERE / "protocol.json"
    if path.exists():
        raise FileExistsError("Immutable timing-prior sweep")
    parent_path = REPORTS / "2026_10_08_position_error_iter32/protocol.json"
    parent = json.loads(parent_path.read_text())
    sources = parent["source_sha256"]
    for f, digest in sources.items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    paths = [*HERE.glob("*.py"), parent_path]
    paths.extend(
        REPORTS / "2026_10_08_position_error_iter32/results" / f"{label}.json"
        for label in parent["cases"]
    )
    for item in paths:
        sources[str(item.relative_to(REPORTS))] = hashlib.sha256(item.read_bytes()).hexdigest()
    plan = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        cases=parent["cases"],
        relative_sigmas_s=[2, 0.5, 0.75, 1],
        scope="Consumed-case initial joint100 diagnostic;001 keeps its oracle-selected region",
        canary="Sigma2 reruns must reproduce both saved starts/arms within1e-5",
        changes="Only relative satellite timing sigma changes; common sigma3 and clocks100 fixed",
        matching="Same bank, observations, calibration, seeds, bounds and20s/600iterations per arm",
        ablation="Both c arms per start; zero-c fixes static c; no RF-time terms at this stage",
        selection="Lowest converged objective per sigma/arm; ties favor original start",
        failure="No local retries; if neither start converges, report unavailable, never omit",
        interpretation="Initial joint fit only; no downstream pruning or deployment claim",
        source_sha256=sources,
    )
    path.write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen", len(sources), "hashes")


if __name__ == "__main__":
    main()
