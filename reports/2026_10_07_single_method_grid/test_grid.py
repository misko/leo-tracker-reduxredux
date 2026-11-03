import math
import unittest
import grid
from leo.analysis.regional_position_search import hierarchical_search

class GridChecks(unittest.TestCase):
    def test_halving_matches_deployed_order_and_scores(self):
        def score(e,n):
            return min((e+81)**2+(n+97)**2+50, (e-130)**2+(n-30)**2+100)
        for budget in (16, 53, 100, 400):
            old = hierarchical_search(score, budget_points=budget)
            new = grid.search(lambda xy: [score(*p) for p in xy],
                              levels=(100.,50.,25.,12.5), budget=budget)
            self.assertEqual(old, new)

    def test_noninteger_children_cover_parent_and_are_deduplicated(self):
        levels = (50.,20.,5.)
        for parent in [grid.Cell(0,10,10), grid.Cell(0,9,10)]:
            children = grid.children(parent, levels)
            e,n = parent.center(levels)
            for x in range(51):
                for y in range(51):
                    px,py=e-25+x,n-25+y
                    self.assertTrue(any(abs(px-c.center(levels)[0]) <= 10+1e-9 and
                                        abs(py-c.center(levels)[1]) <= 10+1e-9 for c in children))
        seen=[]
        def batch(points):
            seen.extend(points)
            return [100 + e*e+n*n for e,n in points]
        result = grid.search(batch, levels=levels)
        self.assertEqual(len(seen),400)
        self.assertEqual(len(set(seen)),400)
        self.assertTrue(all(math.hypot(e,n)<=250 for e,n in seen))
        self.assertEqual(len(result.evaluations),400)

    def test_dense_initial_grid_must_fit_budget(self):
        with self.assertRaisesRegex(ValueError,"484"):
            grid.search(lambda xy: [0.]*len(xy),levels=(20.,10.,5.),budget=400)
        with self.assertRaisesRegex(ValueError,"7860"):
            grid.search(lambda xy: [0.]*len(xy),levels=(5.,),budget=400)

    def test_final_partial_batch_never_exceeds_budget(self):
        seen=[]
        def batch(points):
            seen.extend(points)
            return [e*e+n*n for e,n in points]
        grid.search(batch,levels=(50.,20.,5.),budget=83)
        self.assertEqual(len(seen),83)

if __name__ == "__main__":
    unittest.main(verbosity=2)
