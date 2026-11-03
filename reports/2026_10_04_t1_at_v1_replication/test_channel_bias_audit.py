import unittest
import numpy as np
from channel_bias_audit import channel_basis,controlled_channel_fit


class ChannelBiasTests(unittest.TestCase):
    def test_contrasts_exclude_rx_offsets_and_rf_slope(self):
        rx=np.repeat([0,1],4);ch=np.tile(np.arange(1,5),2);rf=10.5e9+ch*.25e9
        x,basis,_=channel_basis(rf,rx,ch)
        np.testing.assert_allclose(x,basis)
        np.testing.assert_allclose(basis.T@basis,np.eye(5),atol=1e-12)
        np.testing.assert_allclose(basis[:4].sum(axis=0),0.,atol=1e-12)
        np.testing.assert_allclose(basis[4:].sum(axis=0),0.,atol=1e-12)
        np.testing.assert_allclose(((rf-rf.mean())/1e9)@basis,0.,atol=1e-12)
        with self.assertRaises(ValueError):channel_basis(rf[:-1],rx[:-1],ch[:-1])

    def test_quadratic_time_trends_cannot_masquerade_as_channels(self):
        t=np.tile(np.linspace(0,100,80),2);tracks=np.repeat([0,1],80)
        channels=np.tile(np.arange(1,5),40);rx=tracks;rf=10.5e9+channels*.25e9
        x,_,_=channel_basis(rf,rx,channels)
        residual=100+2*t-.04*t*t+30*tracks
        fit=controlled_channel_fit(t,residual,tracks,x)
        np.testing.assert_allclose(fit['coefficients'],0.,atol=1e-8)
        self.assertLess(fit['controlled_rms_hz'],1e-8)
        with self.assertRaises(ValueError):controlled_channel_fit([],[],[],np.empty((0,5)))

    def test_recovers_shared_channel_offsets_with_track_controls(self):
        t=np.tile(np.linspace(0,100,400),4);tracks=np.repeat(np.arange(4),400)
        rx=tracks%2;ch=np.tile(np.arange(1,5),400);rf=10.5e9+ch*.25e9
        x,_,_=channel_basis(rf,rx,ch);expected=np.array([10.,-20.,30.,-40.,50.])
        residual=100+2*t-.04*t*t+30*tracks+x@expected
        fitted=controlled_channel_fit(t,residual,tracks,x,sigma=1e6)
        np.testing.assert_allclose(fitted['coefficients'],expected,atol=1e-6)
        self.assertLess(fitted['channel_corrected_rms_hz'],1e-6)


if __name__=='__main__':unittest.main()
