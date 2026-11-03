import unittest
import numpy as np
from centered import Centered


class Quadratic:
    def evaluate(self, x, gradient=True):
        residual=np.asarray(x)-np.array([.3,-.8,1.2])
        return dict(score=-423000.-float(residual@residual),gradient=-2*residual)


class CenteredTest(unittest.TestCase):
    def test_preserves_score_differences_and_gradients(self):
        raw=Quadratic()
        shifted=Centered(raw,[0.,0.,0.])
        self.assertEqual(shifted.evaluate([0.,0.,0.])['score'],0.)
        points=[[1.,2.,3.],[.3,-.8,1.2]]
        for point in points:
            a,b=raw.evaluate(point),shifted.evaluate(point)
            np.testing.assert_array_equal(a['gradient'],b['gradient'])
            self.assertEqual(a['score'],b['score']+shifted.offset)
        self.assertEqual(raw.evaluate(points[0])['score']-raw.evaluate(points[1])['score'],
                         shifted.evaluate(points[0])['score']-shifted.evaluate(points[1])['score'])


if __name__=='__main__':
    unittest.main()
