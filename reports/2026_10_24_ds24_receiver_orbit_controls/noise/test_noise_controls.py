"""Independent checks of the full held-curve contrast score."""
import json
from pathlib import Path
import unittest
import numpy as np
from noise_controls import contrast_loss, variance, HERE

class NoiseControls(unittest.TestCase):
    def test_constant_variance_matches_exact_projected_density(self):
        t=np.linspace(-1,1,17);design=np.column_stack((np.ones(17),t,t*t))
        q=np.linalg.qr(design,mode='complete')[0][:,3:]
        y=np.sin(9*t)*80.;z=q.T@y
        p=dict(contrast=q,contrast_values=z,margin=np.ones(17))
        law=dict(margin_selected=False,constant_variance=2500.)
        expected=float(z@z/2500+len(z)*np.log(2500.))
        self.assertAlmostEqual(contrast_loss(p,law),expected,places=9)

    def test_affine_and_polynomial_offset_cannot_create_noise_gain(self):
        t=np.linspace(-1,1,21);design=np.column_stack((np.ones(21),t,t*t))
        q=np.linalg.qr(design,mode='complete')[0][:,3:]
        y=np.cos(13*t)*70;offset=design@np.array([3e5,-8e4,2e4])
        law=dict(margin_selected=True,floor=1600.,strength=900.)
        p=dict(contrast=q,contrast_values=q.T@y,margin=np.linspace(.2,1,21))
        shifted=dict(p,contrast_values=q.T@(y+offset))
        self.assertAlmostEqual(contrast_loss(p,law),contrast_loss(shifted,law),places=8)

    def test_all_frozen_group_partitions_are_disjoint(self):
        paths=list((HERE/'results').glob('DS24*.json'));self.assertEqual(len(paths),24)
        for path in paths:
            d=json.loads(path.read_text());allgroups=set(d['folds']);held=[]
            for fold in d['checks']:
                train,test=set(fold['training_groups']),set(fold['test_groups'])
                self.assertFalse(train&test);self.assertEqual(train|test,allgroups);held.extend(test)
            self.assertEqual(len(held),len(set(held)));self.assertEqual(set(held),allgroups)
            self.assertTrue(all(40<=s<=600 for s in d['per_observation_noise_sigma_hz'].values()))

if __name__=='__main__':unittest.main()
