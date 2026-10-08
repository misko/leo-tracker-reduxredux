"""Freeze the selected assembled candidate before reading any reserved outcomes."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def main():
    path = HERE / "protocol.json"
    if path.exists():
        raise FileExistsError("Immutable validation protocol")
    reservation = REPORTS / "2026_10_08_position_error_iter26/newer-random-split.json"
    assignment = json.loads(reservation.read_text())
    selected = REPORTS / "2026_10_08_position_error_iter27/summary.json"
    assert json.loads(selected.read_text())["selected"] == "sigma-0.25"
    sources = {}
    for parent in (
        "2026_10_08_position_error_iter20/validation-protocol.json",
        "2026_10_08_position_error_iter27/protocol.json",
    ):
        old = json.loads((REPORTS / parent).read_text())["source_sha256"]
        for name, digest in old.items():
            assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest
            sources[name] = digest
    for item in [
        *HERE.glob("*.py"),
        reservation,
        selected,
        REPORTS / "2026_10_08_position_error_iter20/pipeline.py",
        REPORTS / "2026_10_08_position_error_iter20/newer.py",
        REPORTS / "2026_10_08_position_error_iter27/results/S41.json",
        REPORTS / "2026_10_08_position_error_iter27/results/DS17-008.json",
    ]:
        sources[str(item.relative_to(REPORTS))] = hashlib.sha256(item.read_bytes()).hexdigest()
    result = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        candidate="Upstream drift-50 pipeline plus matched control refit and slope sigma0.25",
        members=assignment["captures"],
        split_seed=assignment["seed"],
        canaries=["S41", "DS17-008"],
        canary_gate=(
            "Both arms reproduce iteration27 vectors, nuisance coefficients, "
            "objectives and errors within1e-6"
        ),
        development_rule="RESERVED-004 qualifies execution only; no tuning using its error",
        validation_rule="All three random whole scans, no retuning or member replacement",
        primary_gates=dict(
            all_assigned_complete=True,
            fitted_mean_km_strictly_below=1.0,
            fitted_mean_no_worse_than_published_baseline=True,
            fitted_mean_no_worse_than_matched_control=True,
            fitted_worst_no_more_than_baseline_factor=1.1,
            fitted_worst_no_more_than_control_factor=1.1,
            all_final_slope_fitted_converged=True,
        ),
        stage_sequence=(
            "Original plus sep25 regional union; joint100; remove5; post200; drift50; "
            "matched control/slope025"
        ),
        extension_seed=(
            "Converged drift50 fitted; else post200 fitted; else remove5 fitted, "
            "append zero RF terms if needed"
        ),
        centers=(
            "Responsibility-weighted satellite times at the shared fitted seed; "
            "new slopes initially zero"
        ),
        ablation=(
            "Same observations, bank, priors, seed,20s/600iterations per local arm; "
            "zero-c locks static c and both RF-time coefficients"
        ),
        fallback=(
            "Nonstationary slope -> matched control if converged -> previous operational arm; "
            "upstream early stop retained"
        ),
        missing_rule=(
            "Unavailability or execution failure retained and fails completeness; "
            "no substitute member"
        ),
        retries="No local fit retries; existing bounded regional checkpoint slices only",
        scope="Offline checkpoint-backed experiment, not a cold execution or deployment",
        source_sha256=sources,
    )
    path.write_text(json.dumps(result, indent=2) + "\n")
    print("Frozen", len(sources), "source/input hashes and", len(result["members"]), "members")


if __name__ == "__main__":
    main()
