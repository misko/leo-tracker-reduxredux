import copy
import unittest
import numpy as np
import blocks
from evaluate import contrasts


def packet(origin,arm='c0'):
    prior=np.array([1.,2.,3.,4.,5.,6.,7.,8.,.17,11.11111111111111])
    if arm=='fitted_c':prior=np.insert(prior,8,1.)
    return dict(case='test',arm=arm,origin=origin,layout=dict(width=len(prior),members=[0,3,6]),
        noise_precision=[2.,0.,3.] if origin=='original' else [.4,0.,7.],
        coefficient_prior_precision=(prior if origin=='original' else prior*np.r_[np.ones(8),np.ones(len(prior)-8)]).tolist())


class BlockTests(unittest.TestCase):
    def test_exact_crossed_blocks_and_no_mutation(self):
        a=packet('original');b=packet('corrected');b['coefficient_prior_precision'][-2]=.25
        saved=copy.deepcopy((a,b));p=blocks.mixed_packet(a,b)
        self.assertEqual(p['noise_precision'],a['noise_precision'])
        self.assertEqual(p['coefficient_prior_precision'],b['coefficient_prior_precision'])
        p['noise_precision'][0]=100
        self.assertEqual((a,b),saved)
        self.assertFalse(p['nuisance_means_carried']);self.assertFalse(p['phase_reference_carried'])

    def test_same_arm_unit_c_and_physical_constant_mapping(self):
        a=packet('original','fitted_c');b=packet('corrected','fitted_c')
        b['coefficient_prior_precision'][9]=.23
        p=blocks.mixed_packet(b,a)
        reduced=blocks.model.helper_prior(p['coefficient_prior_precision'],'fitted_c')
        self.assertEqual(reduced[-1],11.11111111111111);self.assertEqual(reduced[-2],.17)
        b['coefficient_prior_precision'][8]=1.001
        with self.assertRaises(ValueError):blocks.mixed_packet(a,b)

    def test_refuse_layout_arm_or_inactive_group_change(self):
        for kind in ('arm','layout','inactive','negative'):
            a=packet('original');b=packet('corrected')
            if kind=='arm':b['arm']='fitted_c'
            if kind=='layout':b['layout']['members']=[0,3,7]
            if kind=='inactive':b['noise_precision'][1]=1
            if kind=='negative':a['noise_precision'][0]=-1
            with self.assertRaises(ValueError):blocks.mixed_packet(a,b)

    def test_signed_noise_prior_interaction_and_missing_cell(self):
        x={'00':[0,0],'10':[2,0],'01':[0,3],'11':[3,5]}
        c=contrasts(x)
        np.testing.assert_allclose(c['vectors_km']['interaction'],[1,2])
        np.testing.assert_allclose(np.add(c['vectors_km']['symmetric_noise'],c['vectors_km']['symmetric_prior']),[3,5])
        self.assertFalse(contrasts(dict(x,**{'10':None}))['complete'])


if __name__=='__main__':unittest.main()
