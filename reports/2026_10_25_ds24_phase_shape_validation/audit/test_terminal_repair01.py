import copy
import unittest
import validation_terminal_repair01 as a


class LegacyPhaseTests(unittest.TestCase):
    def legacy(self):return dict(history=[dict(epoch=k,phase_change_s=1e-4/(k+1)) for k in range(5)])

    def test_derive_exact_last_change_without_mutating_source(self):
        saved=self.legacy();before=copy.deepcopy(saved)
        actual=a.canonical_phase_change(saved)
        self.assertEqual(saved,before)
        self.assertNotIn('final_phase_change_s',saved)
        self.assertEqual(actual['final_phase_change_s'],saved['history'][-1]['phase_change_s'])

    def test_reject_missing_history_and_nonfinite_change(self):
        for invalid in ({},dict(history=[]),dict(final_phase_change_s=float('nan'))):
            with self.assertRaises(ValueError):a.canonical_phase_change(invalid)
        invalid=self.legacy();invalid['history'][-1]['phase_change_s']=float('inf')
        with self.assertRaises(ValueError):a.canonical_phase_change(invalid)

    def test_reject_declared_history_conflict(self):
        saved=self.legacy();saved['final_phase_change_s']=.2
        with self.assertRaises(ValueError):a.canonical_phase_change(saved)
        saved['final_phase_change_s']=saved['history'][-1]['phase_change_s']
        self.assertEqual(a.canonical_phase_change(saved),saved)


if __name__=='__main__':unittest.main()
