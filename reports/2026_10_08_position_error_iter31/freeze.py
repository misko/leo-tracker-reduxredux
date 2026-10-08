"""Freeze an explicitly oracle-selected branch diagnosis before its new fits."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    target = HERE / "protocol.json"
    if target.exists():
        raise FileExistsError("Immutable diagnostic protocol")
    parent = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())
    sources = parent["source_sha256"]
    for f, digest in sources.items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    for path in [
        *HERE.glob("*.py"),
        REPORTS / "2026_10_08_position_error_iter29/protocol.json",
        REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json",
        REPORTS / "2026_10_08_position_error_iter29/results/RESERVED-001.json",
        REPORTS / "2026_10_08_position_error_iter30/audit.json",
    ]:
        sources[str(path.relative_to(REPORTS))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        scope=(
            "Oracle diagnostic on consumed RESERVED-001; discarded point chosen using "
            "reference proximity, not a deployable policy or validation result"
        ),
        branches={"retained": [-142.5, -107.5], "discarded": [-80.0, -80.0]},
        question="Can the discarded existing coarse region recover a competitive local solution?",
        canary=(
            "Retained branch first: reproduce published regional winners and iteration29 "
            "final operational vectors, nuisance coefficients, objectives and errors within1e-5"
        ),
        matching=(
            "Same observations, calibration algorithm, association budget60s, "
            "regional/local fit20s/600iterations, hard60 receiver slopes and timing priors"
        ),
        local_radius_km=25,
        radius_note=(
            "Fix25km for both regional branches; native40km cells would use28.284km. "
            "This diagnostic uses the stricter matched radius"
        ),
        final_starts=["association", "zero-timing", "own-continuation"],
        downstream="Same joint100/remove5/post200/drift50/control-refit/slope025 and fallbacks",
        ablation=(
            "Within each branch c arms share bank, all observations, seed rules and budgets; "
            "zero-c locks static c and both RF-time coefficients. Banks may differ by branch"
        ),
        selection=(
            "Within a branch use unchanged regional objective plus calibration penalty. "
            "No operational selection across branches; report their results separately"
        ),
        retry="No local numerical retries; preserve failed diagnostic attempts",
        source_sha256=sources,
    )
    target.write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen", len(sources), "hashes")


if __name__ == "__main__":
    main()
