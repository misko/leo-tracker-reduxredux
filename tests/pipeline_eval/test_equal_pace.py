import copy

import pytest

from tools.pipeline_eval.qualification import equal_pace as trial
from tools.pipeline_eval.qualification import equal_pace_results as results


def test_select_and_order_from_frozen_recording_metadata():
    manifest = dict.fromkeys(trial.EXCLUDED, "00000")
    manifest.update({f"case-{idx:02d}": f"1{idx:02x}" for idx in range(18)})
    assert trial.choose(list(reversed(manifest)), manifest) == (
        "case-00",
        [trial.FOUR, trial.MIXED],
    )
    manifest["case-07"] = "00001"
    assert trial.choose(list(manifest), manifest) == ("case-07", [trial.MIXED, trial.FOUR])
    with pytest.raises(ValueError, match="incomplete"):
        trial.choose(list(manifest)[1:], manifest)


def input_visits():
    centers = [100, None, 100, 200, 100]
    stock = [
        dict(
            visit=i,
            status="processed" if center else "invalid_capture",
            probes=[
                dict(
                    receiver_id=rx,
                    actual_rf_hz=center,
                    candidates=["stock"],
                    visit_index=i,
                    valid_start_counter=i * 200,
                )
                for rx in (0, 1)
            ]
            if center
            else [],
        )
        for i, center in enumerate(centers)
    ]
    fifth = copy.deepcopy(stock)
    for row in fifth:
        for probe in row["probes"]:
            probe["candidates"] = ["fifth"]
    doc = dict(
        delivery_clocks=[dict(monotonic_ns=(i + 1) * 20) for i in range(len(centers))],
        provenance=dict(
            window_count=len(stock),
            excluded_windows=[dict(visit=1, sample_start=200, sample_end=400)],
        ),
        source=dict(
            probe_ms=20, sample_rate_hz=10_000, probes=[p for row in stock for p in row["probes"]]
        ),
    )
    return doc, stock, fifth


def test_mixed_packet_identity_and_counter_include_valid_drops_only():
    doc, stock, fifth = input_visits()
    modes = trial.projected_rows(doc, stock, fifth)
    mixed = modes[trial.MIXED]
    assert [r["fifth_lane"] for r in mixed] == [0, None, 1, 0, 0]
    trace = [
        dict(r, outcome=status)
        for r, status in zip(
            mixed,
            ["queue_drop", "invalid_capture", "emitted", "queue_drop", "emitted"],
            strict=True,
        )
    ]
    probes, visits = results.retained_packets(trace, stock, fifth)
    assert visits == [2, 4]
    assert [p["candidates"][0] for p in probes] == ["stock", "fifth", "fifth", "stock"]
    trace[2]["full_visit_sha256"] = "bad-hash"
    with pytest.raises(ValueError, match="proven emission hash"):
        results.retained_packets(trace, stock, fifth)


def test_projection_rejects_rf_or_visit_metadata_drift():
    doc, stock, fifth = input_visits()
    fifth[2]["probes"][1]["actual_rf_hz"] = 123
    with pytest.raises(ValueError, match="acquisition envelope"):
        trial.projected_rows(doc, stock, fifth)
