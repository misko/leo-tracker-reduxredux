"""Freeze the two existing-start probes; no fit or search settings change."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    target = HERE / "protocol.json"
    if target.exists():
        raise FileExistsError("Immutable probe protocol")
    sources = json.loads((REPORTS / "2026_10_08_position_error_iter31/protocol.json").read_text())[
        "source_sha256"
    ]
    for f, digest in sources.items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    cases = {
        "RESERVED-001": dict(
            document="2026_10_08_position_error_iter31/results/discarded.json",
            nested_document=True,
            basin="point:-80:-80",
            control="2026_10_08_position_error_iter31/results/discarded.json",
            scope="Oracle coarse region; zero-timing start replaces association winner",
        ),
        "RESERVED-003": dict(
            document="2026_10_08_position_error_iter29/baselines/RESERVED-003.json",
            nested_document=False,
            basin="point:-92.5:-82.5",
            control="2026_10_08_position_error_iter29/results/RESERVED-003.json",
            scope="Same operational region/bank; zero-timing start replaces winner",
        ),
    }
    paths = list(HERE.glob("*.py"))
    paths.extend(REPORTS / c[k] for c in cases.values() for k in ("document", "control"))
    for path in paths:
        sources[str(path.relative_to(REPORTS))] = hashlib.sha256(path.read_bytes()).hexdigest()
    protocol = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        cases=cases,
        question="Does joint fitting from the existing zero-timing result retain better positions?",
        scope="Consumed-case diagnostic; not validation or an operational policy",
        unchanged="Observations, bank/calibration, joint models, priors, budgets and fallbacks",
        initialization=(
            "Use existing converged zero-timing regional result for each arm; "
            "downstream uses the fitted start shared between arms exactly as before"
        ),
        ablation="Static-c/RF-time locks; matched banks, seed rules and budgets",
        comparison=(
            "Reuse sealed controls. No retries, score-based cross-bank selection "
            "or reference-error selection"
        ),
        source_sha256=sources,
    )
    target.write_text(json.dumps(protocol, indent=2) + "\n")
    print("Frozen", len(sources), "hashes")


if __name__ == "__main__":
    main()
