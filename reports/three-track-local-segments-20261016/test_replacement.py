import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from rerun import replace_tracks


@dataclass(frozen=True)
class Prepared:
    observations: object
    bootstrap_tracks: tuple=()
    evidence_sha256: str='sha256:'+'1'*64
    trajectory_configuration_sha256: str='sha256:'+'2'*64


class ReplacementTests(unittest.TestCase):
    def test_public_prepared_contract_preserves_observations_and_maps_window_ids(self):
        all_obs=SimpleNamespace(window_ids=('a','b','c','d','e','f'),receiver=[0,1,0,1,0,1])
        low=SimpleNamespace(window_ids=('a','b','e','f'),receiver=[0,1,0,1])
        high=SimpleNamespace(window_ids=('c','d'),receiver=[0,1])
        views={key:Prepared(obs) for key,obs in [('all',all_obs),('low',low),('high',high)]}
        extracted=dict(configuration=dict(window_s=20),selected=[dict(rows=(i,)) for i in range(6)])
        updated,receipt=replace_tracks(views,extracted)
        self.assertEqual(updated['low'].bootstrap_tracks,((0,),(1,),(2,),(3,)))
        for key in views:
            self.assertIs(updated[key].observations,views[key].observations)
            self.assertNotEqual(updated[key].evidence_sha256,views[key].evidence_sha256)
        self.assertTrue(all(r['unchanged_observation_object'] for r in receipt))

    def test_missing_receiver_support_rejected(self):
        obs=SimpleNamespace(window_ids=('a','b'),receiver=[0,1])
        with self.assertRaises(ValueError):
            replace_tracks(dict(all=Prepared(obs)),dict(configuration={},selected=[dict(rows=(0,))]))


if __name__=='__main__':unittest.main()
