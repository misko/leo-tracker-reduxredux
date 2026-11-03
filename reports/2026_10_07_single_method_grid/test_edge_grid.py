import unittest
import grid
import edge_grid

class EdgeChecks(unittest.TestCase):
    def score(self,e,n):return 30000+(e+90)**2+(n+85)**2

    def test_legacy_mode_exactly_reproduces_both_schedules(self):
        for levels in ((100.,50.,25.,12.5),(50.,20.,5.)):
            batch=lambda points:[self.score(*xy) for xy in points]
            old=grid.search(batch,levels=levels)
            new,_=edge_grid.search(batch,levels=levels,edge_policy='legacy-zero')
            self.assertEqual(old,new)

    def test_unknown_edge_priorities_come_from_actual_measurements(self):
        result,meta=edge_grid.search(lambda points:[self.score(*xy) for xy in points],budget=80)
        measured={(r.east_km,r.north_km):r.score for r in result.evaluations}
        self.assertTrue(meta['edge_priorities'])
        for row in meta['edge_priorities']:
            self.assertEqual(row['priority'],measured[tuple(row['nearest_measured'])])
            self.assertGreater(row['priority'],0)

    def test_edges_are_still_explorable_and_budget_is_exact(self):
        result,_=edge_grid.search(lambda points:[(e-244)**2+n*n+1 for e,n in points])
        self.assertEqual(len(result.evaluations),400)
        self.assertTrue(any(r.east_km>240 for r in result.evaluations))
        self.assertEqual(len({(r.east_km,r.north_km) for r in result.evaluations}),400)

if __name__=='__main__':unittest.main(verbosity=2)
