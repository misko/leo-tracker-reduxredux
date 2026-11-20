from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import rescue_attribution as trial
from tools.pipeline_eval.qualification import rescue_attribution_results as results


def fixture():
    agreement = trial.agreement
    cross = trial.support_cross

    def candidate(epoch, margin=0.1, rank=0):
        return dict(
            integer_epoch_sample=epoch,
            fractional_epoch_offset_samples=0.0,
            fractional_tracking_cfo_hz=1250.0,
            fractional_margin=margin,
            candidate_rank=rank,
            passed_fractional_margin_gate=True,
        )

    a, b, x = (candidate(n) for n in (5, 10, 850))
    top = dict.fromkeys(cross.CLOCK_FIELDS, None)
    source = dict.fromkeys(cross.AUTHORITY_FIELDS, "shared")
    source["sample_rate_hz"] = 1_000_000

    def doc(by_visit):
        return dict(
            top,
            provenance={"excluded_windows": []},
            source=dict(
                source,
                probes=[
                    dict(
                        visit_index=i,
                        receiver_id=0,
                        probe_index=i,
                        channel=1,
                        edge="lower",
                        candidates=list(candidates),
                    )
                    for i, candidates in enumerate(by_visit)
                ],
            ),
        )

    stock = doc([[a], [], [], [], []])
    diff = doc([[b], [a], [b], [x], []])
    capture = doc([[a], [a], [a, candidate(10, 0.09, 1)], [], []])
    union = doc([[a], [a], [b], [x], []])
    labels = {}
    for aa, bb, cc in zip(*(d["source"]["probes"] for d in (stock, diff, capture)), strict=True):
        labels[trial.key(aa)] = dict(
            id="site",
            channel="1",
            edge="lower",
            **agreement.classify(
                agreement.best(aa["candidates"]),
                agreement.best(bb["candidates"]),
                cc["candidates"],
                source["sample_rate_hz"] / 750,
            ),
        )
    return stock, diff, capture, union, labels


def test_split_uses_intact_packets_and_accepts_secondary_capture_candidate():
    stock, diff, capture, union, labels = data = fixture()
    snapshot = deepcopy(data)
    groups, audit = trial.partition("site", stock, diff, capture, union, labels)
    left, right = (d["source"]["probes"] for d in (stock, diff))
    assert all(g[0] is left[0] and g[4] is left[4] for g in groups.values())
    assert groups["corroborated"][1] is right[1]
    assert groups["corroborated"][2] is right[2]
    assert groups["remainder"][3] is right[3]
    assert groups["remainder"][1] is left[1] and groups["corroborated"][3] is left[3]
    assert [row["label"] for row in audit] == [
        "capture_winner",
        "other_capture_candidate",
        "capture_negative",
    ]
    assert audit[1]["replacement_packet_sha256"] == trial.digest(right[2])
    assert data == snapshot


def test_split_rejects_replacement_of_stock_positive():
    stock, diff, capture, union, labels = fixture()
    union["source"]["probes"][0] = diff["source"]["probes"][0]
    with pytest.raises(ValueError, match="modified probe packet"):
        trial.partition("site", stock, diff, capture, union, labels)


def test_split_rejects_corrupted_capture_label():
    stock, diff, capture, union, labels = fixture()
    labels[(2, 0, 2)]["hinted"] = "capture_negative"
    with pytest.raises(ValueError, match="family disagrees"):
        trial.partition("site", stock, diff, capture, union, labels)


def test_factorial_contrast_preserves_interaction_and_missing_arms():
    samples = []
    for ident in trial.parent.CASES:
        for arm in results.ARMS:
            for group, score in zip(results.CONDITIONS, (1.0, 1.3, 1.5, 1.4), strict=True):
                samples.append(
                    dict(
                        id=ident,
                        arm=arm,
                        condition=group,
                        error_km=score if arm == "c0" else None,
                        conditional_rf_rms_hz=score,
                        observations=42,
                        tracks=3,
                    )
                )
    effects = {(row["id"], row["arm"], row["metric"]): row for row in results.contrasts(samples)}
    observed = effects["DS26-0168", "c0", "error_km"]
    assert observed["corroborated_vs_stock"] == pytest.approx(0.3)
    assert observed["corroborated_given_remainder"] == pytest.approx(-0.1)
    assert observed["interaction"] == pytest.approx(-0.4)
    assert effects["DS26-0168", "fitted_c", "error_km"]["interaction"] is None
