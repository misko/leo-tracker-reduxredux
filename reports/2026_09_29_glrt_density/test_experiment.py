"""Small tests for the research protocol, independent of saved IQ access."""
import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import evaluate
from evaluate import PERIOD, canonical, match_tracks, reference_choice, panel
from run import partition, sha, write


def candidate(frequency,margin=0.5,rank=0):
    return SimpleNamespace(measured_cfo_hz=frequency,margin=margin,candidate_rank=rank)


def track(intercept=0,rate=-100,start=0,end=10_000_000_000,lane=(1,"upper",0,11_200_000_000.0)):
    return dict(normalized_intercept_hz=intercept,normalized_rate_hz_per_s=rate,
        reference_utc_ns=0,start_utc_ns=start,end_utc_ns=end,lane_key=list(lane))


class ProtocolTests(unittest.TestCase):
    def test_partition_is_order_independent(self):
        rows=[dict(visit_index=i,target_index=i%4,valid_samples=600000) for i in range(100)]
        self.assertEqual(partition(rows),partition(rows[::-1]))
        self.assertEqual(len(partition(rows)),20)

    def test_whole_visit_source_disjointness(self):
        rows=panel()
        self.assertEqual(len(rows),221)
        for a,b in zip(rows,rows[1:]):
            self.assertLessEqual(a["end_counter"],b["start_counter"])
        self.assertEqual(sum(r["partition"]=="evaluation" for r in rows),40)

    def test_duplicate_hypotheses_do_not_fake_ambiguity(self):
        best=candidate(110,0.8)
        selected,reason=reference_choice([candidate(100),best,candidate(PERIOD+105)])
        self.assertIs(selected,best)
        self.assertEqual(reason,"eligible")

    def test_distinct_frequency_branches_abstain(self):
        self.assertEqual(reference_choice([candidate(100),candidate(9000)])[1],"multiple-frequency-clusters")
        self.assertEqual(reference_choice([])[1],"no-passing-candidate")

    def test_reference_selection_does_not_accept_predictions(self):
        with self.assertRaises(TypeError):
            reference_choice([candidate(10)],prediction_hz=20)

    def test_training_only_constant_alias_match(self):
        result=match_tracks([track()],[track(intercept=PERIOD+100)])
        self.assertEqual(len(result["accepted"]),1)
        self.assertAlmostEqual(result["accepted"][0]["shift_hz"],-PERIOD)

    def test_split_and_merge_remain_unmatched(self):
        self.assertEqual(match_tracks([track()],[track(),track(intercept=50)])["accepted"],[])
        self.assertEqual(match_tracks([track(),track(intercept=50)],[track()])["accepted"],[])

    def test_no_cross_receiver_matching(self):
        self.assertEqual(match_tracks([track()],[track(lane=(1,"upper",1,11_200_000_000.0))])["accepted"],[])

    def test_empty_tracks_preserve_failure_inventory(self):
        self.assertEqual(match_tracks([track()],[])["unmatched_left"],[0])
        self.assertEqual(match_tracks([],[])["accepted"],[])

    def test_canonical_branch_boundary(self):
        self.assertAlmostEqual(canonical(PERIOD/2),-PERIOD/2)

    def test_scoring_keeps_eligible_denominator_when_every_track_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"protocol-amendment.md").write_text("frozen")
            write(root/"references.json",dict(amendment_sha256=sha(b"frozen"),rows=[
                dict(reason="eligible",lane=[1,"upper",0,11200000000.0],utc_ns=10,
                     normalized_frequency_hz=100),dict(reason="no-passing-candidate")]))
            for arm in (120,10,20):
                write(root/f"local/tracks-{arm}-training.json",dict(result=dict(tracklets=[])))
            with patch.object(evaluate,"ROOT",root),contextlib.redirect_stdout(io.StringIO()):
                evaluate.score()
            output=json.loads((root/"scores.json").read_text())
            self.assertEqual(len(output["ledger"]),2)
            for summary in output["summary"].values():
                self.assertEqual(summary["eligible_references"],1)
                self.assertEqual(summary["available"],0)
                self.assertIsNone(summary["common_rms_hz"])


if __name__ == "__main__":
    unittest.main()
