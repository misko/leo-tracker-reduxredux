import copy
import inspect
import unittest
from unittest.mock import patch
import numpy as np
import study


def donor(rank,epoch,cfo,margin=.1,status='complete'):
    return dict(candidate_rank=rank,integer_epoch_sample=int(epoch),fractional_epoch_offset_samples=epoch-int(epoch),
        fractional_tracking_cfo_hz=cfo,fractional_margin=margin,fractional_epoch_status=status)


class GuidingTests(unittest.TestCase):
    def test_original_order_not_true_identity_selects_primary(self):
        row=dict(candidates=[donor(5,study.old.EPOCH,study.old.CFO),donor(0,9000,999),donor(1,2,3,-.1)])
        self.assertEqual(study.donors(row)[0]['fractional_tracking_cfo_hz'],999)

    def test_guide_signature_has_no_truth_and_counter_mapping_is_exact(self):
        self.assertNotIn('truth',inspect.signature(study.guide).parameters)
        row=dict(candidates=[donor(0,4321.25,213400)])
        captured=[]
        def score(samples,rate,**kw):
            captured.append(kw)
            from leo.analysis.starlink.fast_scan_scores import PilotMethodScore,PilotMethod
            return PilotMethodScore(PilotMethod.GLRT64,.1,0.,.1,0.,kw['acquired_cfo_hz'])
        with patch('leo.analysis.starlink.fast_scan_scores.conditioned_glrt64_score',score):
            result=study.guide(np.zeros(study.HALF,complex),10_000_000,'lower',row,study.HALF)
        expected=(4321.25-study.HALF)%(10_000_000/750)
        self.assertAlmostEqual(result['primary']['propagated_epoch_samples'],expected)
        self.assertEqual(captured[0]['acquired_cfo_hz'],213400)

    def test_later_support_contains_no_early_samples(self):
        from leo.scanner.fast_scan_analysis import VerifiedFastWindow
        a=dict(sample_start=7000000000,sample_end=7000200000,generation=12)
        w=VerifiedFastWindow(0,'digest',a,{},np.zeros((200000,2,2)),10_000_000)
        values=np.full((100000,2),3+4j)
        late,receipt=study.pack(w,values,100000)
        self.assertEqual(receipt['start_counter'],7000100000)
        self.assertEqual(receipt['stop_counter'],7000200000)
        self.assertEqual(late.samples.shape,(100000,2,2))
        self.assertEqual(late.samples[0,0,0],3)
        self.assertEqual(a['sample_start'],7000000000)

    def test_analytic_phase_is_continuous_across_split(self):
        wave=study.old.analytic(200000,10_000_000,'lower')
        # Re-evaluate a shifted coordinate system analytically, accounting for
        # absolute carrier phase. Independent late synthesis must equal slice.
        later=study.old.analytic(100000,10_000_000,'lower',epoch=study.old.EPOCH-100000)
        later*=np.exp(2j*np.pi*study.old.CFO*.01)
        np.testing.assert_allclose(wave[100000:],later,atol=2e-10)


if __name__=='__main__':unittest.main(verbosity=2)
