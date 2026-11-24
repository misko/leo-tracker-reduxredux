from hashlib import sha256

from reports.ALGO08.v3.compact_cfo_support import FIELDS, estimate, positives


def test_count_positives_only_after_original_stereo_anchor():
    factor = dict(zip(FIELDS, (0, 32, .24, -77230., .29, .04), strict=True), passed_fractional_margin_gate=True)
    probes = [dict(visit_index=visit, receiver_id=rx, edge="lower", channel=4, actual_rf_hz=10.74e9,
                   valid_start_counter=visit*200000, candidates=[] if visit == 1 and rx == 0 else [factor])
              for visit in range(2) for rx in (0, 1)]
    rows = positives(dict(source=dict(session_id="control", probes=probes)))
    assert rows == {"sha256:"+sha256(b"control:1:200000").hexdigest():
                    dict(key=(1, 1), edge="lower", counter=200000, factor=(0, 32, .24, -77230., .29, .04))}


def test_cost_charges_all_positive_packs_and_owner_refills():
    held = dict(positives=20, owners=8, clocks=[dict(clocks=dict(pack=[40_000, 0], gather=[80_000, 0], refill=[72_000, 0]))])
    result = estimate(held, {"north": dict(positives=100, owned_positives=60)})
    assert result["measured_ns_per_lane"] == dict(pack=2000, gather=10000, refill=9000)
    assert result["projections"]["north"] == dict(pack_cpu_s=.0002, refill_cpu_s=.00054,
                                                gather_all_cpu_s=.001, historical_all_positive_cpu_s=.899563848)
