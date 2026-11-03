import unittest
from types import SimpleNamespace
import numpy as np
import experiment as e

class ProtocolChecks(unittest.TestCase):
    def objective(self):
        return SimpleNamespace(prior=SimpleNamespace(radius_km=250.),
            bank=SimpleNamespace(numbers=np.array([1,2]),nodes_s=np.array([-30.,30.])),
            observations=SimpleNamespace(times_s=np.array([-5.,5.])),basis=np.array([[1.],[-1.]])/np.sqrt(2))
    def test_unbounded_baseline_and_hard_bound_after(self):
        v=np.zeros(9);v[3]=119.;g=np.zeros(9)
        self.assertTrue(e.audit(self.objective(),v,g,'zero-c',[0,0],25.,None)['converged'])
        self.assertFalse(e.audit(self.objective(),v,g,'zero-c',[0,0],25.,60.)['feasible'])
        for sign in (-1.,1.):
            v[3]=sign*60.;g[3]=-sign
            self.assertTrue(e.audit(self.objective(),v,g,'zero-c',[0,0],25.,60.)['converged'])
            self.assertFalse(e.audit(self.objective(),v,g,'zero-c',[0,0],25.,None)['converged'])
    def test_region_bounds_and_zero_c(self):
        v=np.zeros(9);v[0]=30.
        self.assertFalse(e.audit(self.objective(),v,np.zeros(9),'zero-c',[0,0],25.,60.)['feasible'])
        self.assertTrue(e.audit(self.objective(),v,np.zeros(9),'zero-c',[0,0],50.,60.)['feasible'])
        v[6]=1.
        self.assertFalse(e.audit(self.objective(),v,np.zeros(9),'zero-c',[0,0],50.,60.)['feasible'])
    def test_both_schedules_use_full_budget_and_correct_edge_priorities(self):
        for phase,cfg in e.PHASES.items():
            search,meta=e.edge_grid.search(lambda points:[1000.+(x+75)**2+(y+75)**2 for x,y in points],
                levels=cfg['levels'],budget=400,edge_policy=cfg['edge'])
            self.assertEqual(len(search.evaluations),400)
            self.assertEqual(len({(p.east_km,p.north_km) for p in search.evaluations}),400)
            self.assertTrue(all(np.hypot(p.east_km,p.north_km)<=250 for p in search.evaluations))
            for edge in meta['edge_priorities']:
                self.assertEqual(edge['priority'],0. if phase=='before' else edge['nearest_score'])
if __name__=='__main__':unittest.main(verbosity=2)
