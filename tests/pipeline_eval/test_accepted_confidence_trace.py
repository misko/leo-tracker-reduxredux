import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.accepted_confidence_trace import ConfidenceTrace, binding, fingerprint, summarize


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


def test_hash_uses_order_shape_dtype_and_signed_zero():
    row = np.array([0., 3.])
    assert fingerprint(row) == fingerprint(row.copy())
    for different in (row[::-1], row.reshape(1, 2), row.astype(np.float32), [-0., 3.],
                      np.array([-0., 3.]), row.astype(">f8")):
        assert fingerprint(row) != fingerprint(different)


@pytest.mark.parametrize("capacity", (None, 0, 32*2**20))
def test_live_confidence_keeps_values_and_separates_projection_from_receiver_nuisance(monkeypatch, capacity):
    monkeypatch.syspath_prepend(str(HERE))
    import lighter_joint_estimator as estimator
    from accepted_confidence_projection_reuse import ProjectionReuse

    saved = json.loads((HERE/"measurements/accepted-lean-small-operands.json").read_bytes())
    t, values = np.array(saved["times"]), np.array(saved["values"])
    offsets = np.arange(0., 401., 100.)
    p = np.stack([np.column_stack((np.full(len(offsets), 6900.), offsets*sk, offsets*sk/3))
                  for sk in (1., 2.)])
    v = np.broadcast_to([[0., 1., 1./3.], [0., 2., 2./3.]], (len(offsets), 2, 3)).transpose(1, 0, 2)
    scan = SimpleNamespace(
        norads=np.array([1, 2]), origin_utc_ns=0, radio_sigma_hz=150.,
        sky=dict(position_km=p, velocity_km_s=v, time_s=offsets),
        times=t, hardware=lambda track, beta: beta[0]*np.sqrt(track["times"]),
        rx_basis=[np.ones((len(t), 1))]*2,
        search_region=SimpleNamespace(half_width_km=20., latlon=lambda pair: tuple(pair/100.)),
    )
    scan.tracks = [dict(key=f"lane{i}", receiver=1, channel=i+1, rf_hz=(i+113)*1e8,
                        values=values-i*100, times=t) for i in range(2)]
    node = dict(seed=dict(rows=[dict(component=track["key"], active_curvature=True, candidate_index=0)
                                for track in scan.tracks]))
    beta = np.array([0.0])

    def problem(scan, node, arm, keep, reference):
        return SimpleNamespace(keep=keep, reference=reference,
                               state=lambda _: dict(beta=beta, smooth=[np.zeros(1)]*2))

    monkeypatch.setattr(estimator, "problem", problem)
    monkeypatch.setattr(estimator, "phase_widths", lambda *_: (np.array([1., 2.]), []))
    keep = np.ones(2*len(t), bool)
    baseline = {"arms": {"c0": {"record": dict(phase_reference=np.zeros(1), endpoint_east_north_km=np.zeros(2))}}}
    original = estimator.minimum_confidence
    expected = original(scan, node, keep, baseline, receipts=[])
    trace = ConfidenceTrace() if capacity is None else ProjectionReuse(byte_limit=capacity)
    receipts = []
    with binding(estimator, trace):
        for _ in range(2):
            assert estimator.minimum_confidence(scan, node, keep, baseline, receipts=receipts).tobytes() == expected.tobytes()
        beta[0] = 1.0
        assert estimator.minimum_confidence(scan, node, keep, baseline, receipts=receipts).tobytes() == original(
            scan, node, keep, baseline, receipts=[]).tobytes()
        keep[0] = keep[len(t)] = False
        assert estimator.minimum_confidence(scan, node, keep, baseline, receipts=receipts).tobytes() == original(
            scan, node, keep, baseline, receipts=[]).tobytes()

    assert estimator.minimum_confidence is original
    assert len(receipts) == len(trace.records) == 4
    first, duplicate, changed_radio, changed_epochs = trace.records
    assert first["nuisance"] == duplicate["nuisance"] != changed_radio["nuisance"]
    assert first["epochs"] == changed_radio["epochs"] != changed_epochs["epochs"]
    assert first["prepared_geometry"] == changed_radio["prepared_geometry"] != changed_epochs["prepared_geometry"]
    totals = summarize(trace.records)
    assert totals["stages"]["project"]["calls"] == 20
    assert totals["stages"]["profile"]["calls"] == 40
    assert len(totals["exact_input_repeats"]["projections"]) == 10
    assert len(totals["exact_input_repeats"]["profiles"]) == 10
    assert all(row["output_identical"] for rows in totals["exact_input_repeats"].values() for row in rows)
    if capacity is not None:
        assert trace.original_calls == (10 if capacity else 20)
        assert trace.hits == (10 if capacity else 0)
        assert trace.held_bytes <= capacity
