import unittest
import numpy as np
from east_west_sanity import enu_frame, sky, wrong_side, path_class, crossing_order


class GeometryTests(unittest.TestCase):
    def test_cardinal_directions_and_axes(self):
        origin, rotation=enu_frame(37.,-122.)
        for rx,sign in [(0,-1),(1,1)]:
            vector=np.array([sign*np.sin(np.deg2rad(20)),0.,np.cos(np.deg2rad(20))])
            xyz=origin+1000*(vector@rotation)
            b,e,off=sky(np.array([0.,1.]),np.array([xyz,xyz]),np.array([.5]),origin,rotation)
            self.assertAlmostEqual(b[0],sign*20.)
            self.assertAlmostEqual(e[0],70.)
            self.assertAlmostEqual(off[0,rx],0.,places=5)
            self.assertAlmostEqual(off[0,1-rx],40.)
            self.assertFalse(wrong_side(b,np.array([rx]))[0])
            self.assertTrue(wrong_side(b,np.array([1-rx]),10.)[0])

    def test_crossing_and_guard(self):
        self.assertEqual(path_class(np.array([-20.,20.])), 'W→E')
        self.assertEqual(path_class(np.array([20.,-20.])), 'E→W')
        self.assertEqual(path_class(np.array([20.,5.])), 'East only')
        self.assertEqual(path_class(np.array([-20.,5.,-20.])), 'Multiple crossings')
        self.assertFalse(wrong_side(np.array([5.]),np.array([0]),10.)[0])

    def test_median_order_has_tie_tolerance(self):
        t=np.arange(10.)
        self.assertEqual(crossing_order('W→E',t,t+1e-8),'tied within 20 ms')
        self.assertEqual(crossing_order('W→E',t,t+10),'consistent')
        self.assertEqual(crossing_order('E→W',t,t+10),'reversed')
        self.assertEqual(crossing_order('E→W',t[:5],t),'not testable')

    def test_no_extrapolation(self):
        origin,rotation=enu_frame(0.,0.)
        with self.assertRaises(ValueError):
            sky(np.array([0.,1.]),np.ones((2,3)),np.array([2.]),origin,rotation)


if __name__=='__main__': unittest.main()
