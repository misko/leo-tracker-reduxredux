"""Receipt tests require the completed first local development shard."""
import copy
import json
from pathlib import Path
import unittest
from verify_grouped_rebuild import verify


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved=json.loads((Path(__file__).resolve().parent/'grouped-rebuild-scan-fw-39ac2b14d1bb5f0f.json').read_text())

    def test_completed_receipt(self):
        result=verify(self.saved)
        self.assertEqual(result['supported_tracks']+result['unsupported_tracks'],62)

    def test_score_tampering_rejected(self):
        bad=copy.deepcopy(self.saved);bad['records'][0]['controls']['normal']['nll']+=1
        with self.assertRaises(ValueError):verify(bad)

    def test_overlap_rejected(self):
        bad=copy.deepcopy(self.saved);r=bad['records'][0]
        r['held_observation_ids'][0]=r['training_observation_ids'][0]
        with self.assertRaises(ValueError):verify(bad)

    def test_missing_direction_rejected(self):
        bad=copy.deepcopy(self.saved);bad['records'].pop()
        with self.assertRaises(ValueError):verify(bad)


if __name__=='__main__':unittest.main()
