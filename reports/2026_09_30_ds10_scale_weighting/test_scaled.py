import unittest
import numpy as np
from scaled_model import Scaled,helper,trend_module


class Engine:
    def __init__(self,doc,config):pass
    def coordinates(self,x):return tuple(x[:2])
    def prediction(self,track,x):
        t=np.asarray(track['times_s'])
        return np.array([x[0]*t+x[1]*t*t+x[2],-x[0]*t+.3*x[2]*t]),np.array([True,True])


def document():
    return [dict(session_id='s',tracks=[dict(track_id='t',times_s=[0.,1.,2.,3.,4.],
                                          y=np.array([50.,90.,180.,160.,210.]),mask=np.array([True,False,True,False,True]))])]


class ScaleTest(unittest.TestCase):
    def test_unity_equivalence(self):
        docs=document();x=[2.,1.,3.]
        a=helper.TrendMixturePosition(docs,{},Engine,.2).evaluate(x,held=True)
        b=Scaled(docs,{}, {},Engine).evaluate(x,held=True)
        self.assertEqual(a['score'],b['score'])
        self.assertEqual(a['rows'],b['rows'])
        np.testing.assert_array_equal(a['gradient'],b['gradient'])

    def test_direct_density_and_jacobian(self):
        docs=document();x=[2.,1.,3.];r=1.7
        model=Scaled(docs,{}, {('s','t'):r},Engine)
        got=model.evaluate(x,held=True)
        track=docs[0]['tracks'][0];prediction,_=Engine({},{}).prediction(track,x)
        residual=track['y'][None,:]-prediction
        scores=[]
        for mask in [track['mask'],np.ones(5,bool)]:
            signal,_=trend_module.contrast_density(residual[:,mask],100*r)
            bg=trend_module.trend_density(track['y'][mask],np.asarray(track['times_s'])[mask],100*r,2000.)
            scores.append(np.logaddexp(np.log(.8)+np.logaddexp.reduce(signal)-np.log(2),np.log(.2)+bg))
        self.assertAlmostEqual(got['score'],scores[0],places=10)
        self.assertAlmostEqual(got['rows'][0]['held_log_score'],scores[1]-scores[0],places=10)
        for i in range(3):
            delta=np.zeros(3);delta[i]=1e-4
            fd=(model.evaluate(np.array(x)+delta,gradient=False)['score']-model.evaluate(np.array(x)-delta,gradient=False)['score'])/(2e-4)
            self.assertAlmostEqual(got['gradient'][i],fd,places=7)


if __name__=='__main__':unittest.main()
