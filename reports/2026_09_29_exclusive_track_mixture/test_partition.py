import itertools
import math
import unittest
import numpy as np
from partition import Partition


class PartitionTest(unittest.TestCase):
    def test_no_conflicts_reduces_to_old_mixture(self):
        graph=Partition([['a'],['b'],['c']]);f=np.array([-3.,-8.,-1.]);b=np.array([-5.,-2.,-7.])
        score,weights=graph.density(f,b)
        terms=np.logaddexp(math.log(.8)+f,math.log(.2)+b)
        self.assertAlmostEqual(score,float(terms.sum()),places=12)
        np.testing.assert_allclose(weights,np.exp(math.log(.8)+f-terms))

    def test_fixed_dimension_density_normalizes(self):
        graph=Partition([['a'],['a']]);total=0.
        signal=[.8,.7];background=[.3,.2]
        for y in itertools.product((0,1),repeat=2):
            f=np.log([p if z else 1-p for p,z in zip(signal,y)])
            b=np.log([p if z else 1-p for p,z in zip(background,y)])
            value,weights=graph.density(f,b);total+=math.exp(value)
            self.assertLessEqual(weights.sum(),1+1e-12)
        self.assertAlmostEqual(total,1.,places=12)

    def test_partition_gradient_and_component_cap(self):
        graph=Partition([['a'],['a','b'],['b'],['c']]);x=np.array([3.,-2.,1.,4.]);_,g=graph.evaluate(x)
        for i in range(4):
            d=np.zeros(4);d[i]=1e-5
            self.assertAlmostEqual(g[i],(graph.evaluate(x+d)[0]-graph.evaluate(x-d)[0])/2e-5,places=8)
        with self.assertRaises(ValueError):Partition([['x']]*13)


if __name__=='__main__':unittest.main()
