import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import expansion


class ExpansionTests(unittest.TestCase):
    def test_reused_R01_math_and_adapter_match_sealed_sources(self):
        math,adapter=expansion.frozen_modules()
        self.assertEqual(math.MODE_CAP,8);self.assertEqual(math.GATE,.025)
        self.assertEqual(list(math.COARSE),list(range(-256,257,8)))

    def test_global_parity_reuse_never_claims_fresh_window_parity(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'index';path.write_bytes(b'index')
            acquisition={'sample_start':0,'sample_end':10};target={'channel':5}
            window=SimpleNamespace(iq_sha256='iq',acquisition=acquisition,target=target,sample_rate_hz=10_000_000,samples=np.zeros((10,2,2)))
            exhausted=[]
            def windows():yield window;exhausted.append(True)
            port=SimpleNamespace(windows=windows,receiver_ids=(0,1))
            a=dict(index_path=str(path),index_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(),
                index=dict(iq_sha256='iq',acquisition=acquisition),target=target,segment={},local_sequence=0,sample_rate_hz=10_000_000)
            with patch('leo.storage.fast_scan.FastSegmentSource',return_value=port):
                _,_,_,receipt=expansion.open_native({'raw_authority':a})
            self.assertEqual(exhausted,[True]);self.assertFalse(receipt['fresh_per_window_paired_candidate_parity'])
            self.assertEqual(receipt['repeated_blind_acquisition_calls'],0)


if __name__=='__main__':unittest.main(verbosity=2)
