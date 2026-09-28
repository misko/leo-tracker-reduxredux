"""Requires both completed fixed-candidate component-audit receipts."""
import hashlib
import json
import math
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    def test_component_parity_and_binding(self):
        for sid in ('scan-fw-127d8fc36e804ae2','scan-fw-8f4f960d9db67798'):
            raw=(HERE/f'disjoint-{sid}.json').read_bytes()
            audit=json.loads((HERE/f'failure-components-{sid}.json').read_text())
            self.assertEqual(audit['source_sha256'],'sha256:'+hashlib.sha256(raw).hexdigest())
            original={r['track_id']:r for r in json.loads(raw)['records'] if r['direction']=='X_to_Y'}
            self.assertEqual(len(audit['tracks']),2)
            for r in audit['tracks']:
                self.assertEqual(r['candidate_ids'],original[r['track_id']]['candidate_ids'])
                expected=original[r['track_id']]['controls']['normal']['reception_ll']
                for d,q,v in zip(r['detection_ll'],r['ratio_ll'],expected):self.assertAlmostEqual(d+q,v,places=8)
                for f in r['frequency']:
                    self.assertAlmostEqual(f['held_refit_cfo_hz']-f['conditioning_cfo_hz'],f['cfo_difference_hz'],places=8)
                    self.assertTrue(math.isfinite(f['held_fixed_rms_hz']))
                    self.assertTrue(math.isfinite(f['held_refit_rms_hz']))


if __name__=='__main__':unittest.main()
