import unittest
import numpy as np
from scipy.special import logsumexp
from model import JointOrbit,direction,fast
class Geometry:
    def __init__(self,doc,config):pass
    def prediction(self,track,x):return track['base']+np.einsum('cnk,k->cn',track['jac'],x),np.ones(len(track['base']),bool)
def fixture():
    rng=np.random.default_rng(14);tracks=[];older=[]
    for tid in ('a','b'):
        t=dict(track_id=tid,y=rng.normal(0,70,10),mask=np.arange(10)<8,times_s=list(range(10)),catalogue_size=40,
               base=rng.normal(0,40,(2,10)),jac=rng.normal(0,8,(2,10,3)))
        tracks.append(t);older.append(dict(t,base=t['base']+rng.normal(0,80,(2,10)),jac=t['jac']+rng.normal(0,2,(2,10,3))))
    return dict(tracks=tracks),dict(tracks=older)
class JointTests(unittest.TestCase):
    def test_gradients_and_held_isolation(self):
        doc,old=fixture();mapping={'a':[1,2],'b':[1,2]};groups=[dict(track_ids=['a','b'],candidate_norad=[1,2])]
        for variant in ('zero','orbit','linear'):
            m=JointOrbit(doc,old,{},mapping,groups,[],variant,[1/6]*6,Geometry);x=np.array([.2,-.1,.1]);r=m.evaluate(x)
            for axis in range(3):
                d=np.eye(3)[axis]*1e-4
                finite=(m.evaluate(x+d,False)['score']-m.evaluate(x-d,False)['score'])/2e-4
                self.assertAlmostEqual(finite,r['gradient'][axis],places=5)
            doc['tracks'][0]['y'][8:]+=1e5
            self.assertAlmostEqual(m.evaluate(x)['score'],r['score'],places=10)
    def test_zero_matches_shared_identity_sum(self):
        doc,old=fixture();mapping={'a':[1,2],'b':[1,2]};groups=[dict(track_ids=['a','b'],candidate_norad=[1,2])]
        m=JointOrbit(doc,old,{},mapping,groups,[],'zero',[1/6]*6,Geometry)
        scores=[fast.profile(t['y'][None,:]-t['base'],t['mask'])[0] for t in doc['tracks']]
        self.assertAlmostEqual(m.evaluate(np.zeros(3))['score'],logsumexp(sum(scores))-np.log(40),places=10)
    def test_linear_direction_rms_and_center(self):
        t=np.arange(10.);mask=t<8;d=np.array([t*t]);j=np.zeros((1,10,3))
        out,_=direction(d,j,t,mask,True)
        self.assertAlmostEqual(out[:,mask].mean(),0.)
        self.assertAlmostEqual(float(np.mean(out[:,mask]**2)),float(np.var(d[:,mask])))
