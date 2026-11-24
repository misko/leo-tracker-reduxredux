import json
from pathlib import Path

import pytest

from reports.ALGO08.v3.receiver_mix_budget import predict, schedule


def probe_pair(visit, channel):
    return [dict(visit_index=visit, valid_start_counter=visit * 100, edge="lower",
                 channel=channel, actual_rf_hz=11e9, receiver_id=radio) for radio in (0, 1)]


def test_each_channel_starts_on_a_full_anchor_and_uses_both_radios():
    probes = [row for i in range(10) for row in probe_pair(i, 2 if i == 5 else 1)]
    counts, streams = schedule(probes)
    assert counts == {"full": 6, "short_primary": 14}
    assert [s["admitted"] for s in streams] == [9, 1]
    with pytest.raises(ValueError, match="Incomplete"):
        schedule(probes[:-1])
    with pytest.raises(ValueError, match="Nonchronological"):
        schedule(probes + probe_pair(1, 1))
    probes[-1]["edge"] = "upper"
    with pytest.raises(ValueError, match="Mismatched"):
        schedule(probes)


def test_native_cpu_and_remaining_cpu_have_separate_denominators():
    donor = dict(cpu_s_per_call={"full": .5, "short_primary": .2}, other_cpu_s_per_byte=.01)
    target = dict(calls={"full": 2, "short_primary": 8}, encoded_bytes=200)
    assert predict(donor, target) == pytest.approx(4.6)


def test_portable_budget_reproduces_self_clocks_and_target_scenarios():
    path = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements/receiver-mix-budget.json"
    study = json.loads(path.read_bytes())
    for source in study["measured"]:
        assert predict(source, source) == pytest.approx(source["cpu_s"])
    assert [r["case"] for r in study["projected"]] == ["DS30-0163", "DS30-0173", "DS30-0359"]
    for target in study["projected"]:
        for source in study["measured"]:
            assert predict(source, target) == pytest.approx(target["transfer"][source["name"]])
    final = study["projected"][-1]
    assert final["calls"] == {"full": 1296, "short_primary": 9024}
    assert min(final["remaining_s"].values()) == pytest.approx(.243, abs=.001)
