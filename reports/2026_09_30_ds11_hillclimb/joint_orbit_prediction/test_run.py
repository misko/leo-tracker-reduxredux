import importlib.util
from pathlib import Path
import unittest
import numpy as np
from run import predictive,JointOrbit
spec=importlib.util.spec_from_file_location('joint_test_helpers',Path(__file__).resolve().parents[1]/'joint_orbit_uncertainty/test_model.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
class PredictionTests(unittest.TestCase):
    def test_training_replay_and_held_no_feedback(self):
        doc,old=helpers.fixture();groups=[dict(track_ids=['a','b'],candidate_norad=[1,2])]
        model=JointOrbit(doc,old,{},dict(a=[1,2],b=[1,2]),groups,[],'orbit',[1/6]*6,helpers.Geometry)
        x=np.zeros(3);a=predictive(model,x)
        self.assertAlmostEqual(a['training_score'],model.evaluate(x)['score'],places=9)
        doc['tracks'][0]['y'][8:]+=1000
        b=predictive(model,x)
        self.assertEqual(a['training_score'],b['training_score'])
        self.assertNotEqual(a['held_score'],b['held_score'])
    def test_zero_direction_prior_cancels(self):
        doc,_=helpers.fixture();mapping=dict(a=[1,2],b=[1,2]);groups=[dict(track_ids=['a','b'],candidate_norad=[1,2])]
        zero=JointOrbit(doc,doc,{},mapping,groups,[],'zero',[1/6]*6,helpers.Geometry)
        orbit=JointOrbit(doc,doc,{},mapping,groups,[],'orbit',[1/6]*6,helpers.Geometry)
        a=predictive(zero,np.zeros(3));b=predictive(orbit,np.zeros(3))
        self.assertAlmostEqual(a['held_score'],b['held_score'],places=9)
