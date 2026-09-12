"""Tiny known-shift comparison fixture, independent of RF and storage."""

from leo.contracts.scanner_refinement import (
    PROFILES,
    ComparisonCandidateV1,
    ComparisonEvidenceV1,
    ComparisonEvidenceV2,
    ComparisonRowV1,
)


def comparison_fixture(*, sample_rate_hz=5000000):
    rows = []
    for case, amount in (("baseline", 0.0), ("frequency", 137.123), ("delay", 71.31)):
        for i, profile in enumerate(PROFILES):
            cfo = 10000 + (
                amount + [80, 6, 0.5, 0.2][i]
                if case == "frequency"
                else [100, 5, 1, 0.2][i]
                if case == "delay"
                else 0
            )
            epoch = 0.0001 + ((amount + [20, 20, 20, 2][i]) * 1e-9 if case == "delay" else 0)
            rows.append(
                ComparisonRowV1(
                    probe_id="scan-one:0:0",
                    visit_index=0,
                    receiver_id=0,
                    target_index=0,
                    time_s=1,
                    profile=profile,
                    case=case,
                    amount=amount,
                    candidates=(
                        ComparisonCandidateV1(
                            rank=0,
                            integer_epoch_s=0.0001,
                            epoch_s=epoch,
                            cfo_hz=cfo,
                            exact_score=0.8,
                            margin=0.6,
                        ),
                    ),
                    selected_rank=0,
                    acquisition_seconds=0.1,
                    scoring_seconds=0.01,
                )
            )
    model = ComparisonEvidenceV2 if sample_rate_hz == 10000000 else ComparisonEvidenceV1
    return model(
        session_id="scan-one",
        session_kind="fixed",
        input_manifest_sha256="sha256:" + "a" * 64,
        implementation_sha256="sha256:" + "b" * 64,
        sample_rate_hz=sample_rate_hz,
        scheduled_probe_ids=("scan-one:0:0",),
        rows=tuple(rows),
    )
