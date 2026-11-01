import unittest
import numpy as np
from reconsider import masks,rank_families,OUT,INPUT,ARMS,read,reconstruct
from transfer import gaussian_predict

class NumericalTests(unittest.TestCase):
    def test_predictive_matches_dense_covariance(self):
        rng=np.random.default_rng(9);X=rng.normal(size=(30,4));y=rng.normal(size=30);train=np.arange(30)<20;test=~train;sigma=2.
        r=gaussian_predict(y,X,train,test,sigma)
        C=np.linalg.inv(np.eye(4)+X[train].T@X[train]/sigma**2);b=C@X[train].T@y[train]/sigma**2
        V=np.eye(sum(test))*sigma**2+X[test]@C@X[test].T;res=y[test]-X[test]@b
        expected=res@np.linalg.solve(V,res)+np.linalg.slogdet(V)[1]+sum(test)*np.log(2*np.pi)
        self.assertAlmostEqual(r['score'],expected,places=10)
    def test_held_values_cannot_change_training_coefficients(self):
        rng=np.random.default_rng(10);X=rng.normal(size=(30,4));y=rng.normal(size=30);train=np.arange(30)<20;test=~train
        original=gaussian_predict(y,X,train,test);y[test]+=1000;changed=gaussian_predict(y,X,train,test)
        np.testing.assert_array_equal(original['posterior_coefficient'],changed['posterior_coefficient'])
        self.assertNotEqual(original['score'],changed['score'])
    def test_random_masks_synchronize_and_guard(self):
        times=np.tile(np.arange(0,100,.5),3);group=np.repeat(np.arange(3),200)
        splits=masks(times,group);self.assertEqual(len(splits),5)
        distinct=masks(times,group,unique=True)
        self.assertEqual(len({tuple(r['held_blocks']) for r in distinct}),5)
        for r in splits:
            self.assertFalse(np.any(r['train']&r['test']))
            blocks=np.floor(times/5).astype(int)
            self.assertFalse(np.any(np.isin(blocks[r['train']],np.r_[r['held_blocks']-1,r['held_blocks'],r['held_blocks']+1])))
            for k in (1,2):np.testing.assert_array_equal(r['test'][:200],r['test'][k*200:(k+1)*200])
    def test_zero_features_predict_prior_noise(self):
        y=np.array([0.,1.,2.,3.]);X=np.zeros((4,2));train=np.array([True,True,False,False]);r=gaussian_predict(y,X,train,~train,2.)
        np.testing.assert_allclose(r['predictive_sigma_hz'],2.)
        self.assertAlmostEqual(r['score'],13/4+2*np.log(8*np.pi))
    def test_completed_trials_preserve_native_fit_evidence(self):
        protocol=read(OUT/'protocol.json')
        for case in protocol['development']+protocol['validation']:
            z=read(INPUT/(case+'.json'));d=reconstruct(z);base=d['problems']['fitted_c'][0]
            expected={o for i,sl in zip(base.members,base.slices) for o,use in zip(base.scan.tracks[i]['observation_ids'],base.keep[sl]) if use}
            result=read(OUT/case/'result.json')
            for record in result['records']:
                for row in record['rows']:
                    if row['status']!='complete':continue
                    ids=[o for tr in row['tracks'] for o in tr['observation_ids']]
                    self.assertEqual(len(ids),len(set(ids)));self.assertEqual(set(ids),expected)
                    if row['qualified']:
                        self.assertTrue(row['all_gates_pass'] and row['phase_closed'] and row['optimizer_success'])
                        self.assertFalse(row['lost_ids']);self.assertFalse(row['unexpected_reassigned_ids'])
            if result['selected']:
                record=next(r for r in result['records'] if r['hypothesis']['name']==result['selected'])
                self.assertTrue(record['prediction_pass']);self.assertNotIn('prediction_limit',record['hypothesis'])
                self.assertTrue(all(record['paired_gain'][a]>0 for a in ARMS))
            else:
                for a in ARMS:self.assertEqual(result['baseline'][a],result['final'][a])

if __name__=='__main__':unittest.main()
