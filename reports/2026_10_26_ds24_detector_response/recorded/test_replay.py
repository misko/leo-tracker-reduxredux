import unittest
from types import SimpleNamespace
import replay


def candidate(rank=0,cfo=100.):
    return dict(candidate_rank=rank,integer_epoch_sample=127,passed_fractional_margin_gate=True,
        fractional_epoch_offset_samples=.25,fractional_tracking_cfo_hz=cfo,
        fractional_exact_score=.2,fractional_control_score=.1,fractional_margin=.1)


class ReplayTests(unittest.TestCase):
    def test_all_candidates_and_count_must_match(self):
        a=[candidate(),candidate(1,200.)]
        self.assertTrue(replay.compare(a,a)['all_passed'])
        self.assertFalse(replay.compare(a,a[:1])['all_passed'])
        changed=[candidate(),candidate(1,201.)]
        self.assertFalse(replay.compare(a,changed)['all_passed'])

    def test_gate_and_rank_not_relaxed(self):
        a=candidate();b=dict(a,passed_fractional_margin_gate=False)
        self.assertFalse(replay.compare([a],[b])['all_passed'])
        rx=SimpleNamespace(receiver_id=1,candidates=[SimpleNamespace(candidate_rank=0),SimpleNamespace(candidate_rank=2)])
        self.assertEqual(replay.fixed_rank([rx],1,2).candidate_rank,2)
        with self.assertRaises(ValueError):replay.fixed_rank([rx],1,1)

    def test_public_iterator_is_fully_exhausted(self):
        class Source:
            checked=False
            def windows(self):
                yield 'one'
                self.checked=True
        s=Source();self.assertEqual(replay.exhaust_one(s),'one');self.assertTrue(s.checked)

    def test_failure_keeps_exact_denominator_without_replacement(self):
        requests=[dict(request_id=str(i),case='case',role='target',complete_owner='owner')for i in range(8)]
        records=[dict(request_id='0',status='complete'),dict(request_id='1',status='failed')]
        result=replay.complete_slots(requests,records,'stopped')
        self.assertEqual(len(result),8);self.assertEqual(sum(r['status']=='not_attempted'for r in result),6)
        self.assertEqual([r['request_id']for r in result],list(map(str,range(8))))


if __name__=='__main__':unittest.main()
