"""Component tests for the paid-prefix history gate."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from prefix_history_gate import CHECKPOINT, count_plan, decide, paid_prefix, potential_rollback


def opportunity(i, radio, channel=1):
    return dict(visit_index=i, receiver_id=radio, edge="lower", channel=channel,
                actual_rf_hz=6_000_000_000+channel, valid_start_counter=100*i,
                candidates=[dict(passed_fractional_margin_gate=True)])


class GateTests(unittest.TestCase):
    def test_future_factors_cannot_enter_the_prefix(self):
        rows = [opportunity(visit, radio) for visit in (0,511,512) for radio in (0,1)]
        original = paid_prefix(rows,800)
        rows[4]["candidates"] = []
        rows[5]["candidates"] = [{"another_future_value":True}]
        self.assertEqual(paid_prefix(rows,800), original)
        self.assertEqual(original["provenance"], dict(window_count=512, processed_windows=2, invalid_capture=510))
        self.assertEqual(decide(paid_prefix(rows,20))["route"], "full-guarded")

    def test_admission_needs_every_radio_block_to_agree_and_have_support(self):
        rows = [opportunity(visit,radio) for visit in range(CHECKPOINT) for radio in (0,1)]
        stub = dict(route="unfiltered", cycles=[
            dict(visit=128*block+cycle*8, radio=radio, stream=("lower",1,6000000001),
                 outcome=cycle%2, delta_log_score=-.5)
            for block in range(4) for radio in (0,1) for cycle in range(8)
        ], log_score_gain_by_radio={0:-16.,1:-16.}, incomplete_cycles={},
            prediction_digest="test", radio={0:{"held":32},1:{"held":32}})
        prefix = paid_prefix(rows,800)
        with patch("prefix_history_gate.select_route",return_value=stub):
            self.assertEqual(decide(prefix)["route"], "thin-unfiltered")
            stub["cycles"][-1]["delta_log_score"] = 4.
            self.assertEqual(decide(prefix)["reason"], "history_or_inconsistent_sign")
            stub["cycles"].pop()
            self.assertEqual(decide(prefix)["reason"], "insufficient_support")

    def test_unknown_stream_never_thins_and_full_anchors_stay_paid(self):
        rows = [opportunity(visit,radio,channel) for visit in range(540)
                for channel in [1 if visit<520 or visit%2 else 2] for radio in (0,1)]
        plan = count_plan({"source":{"probes":rows}}, dict(route="thin-unfiltered", observed_streams=[
            {"stream":("lower",1,6000000001)}]))
        decision = plan["skipped_visits_if_allowed"]
        self.assertTrue(decision)
        self.assertTrue(all(visit>=512 and (visit<520 or visit%2) for visit in decision))
        self.assertNotIn(512,decision)
        self.assertEqual(plan["actual_skipped_lanes"], 2*len(decision))
        replay = potential_rollback(plan,{"potential_gross_cpu_s":.1})
        self.assertEqual(replay["full_stereo_iq_bytes"],len(decision)*1_600_000)


if __name__ == "__main__":
    unittest.main()
