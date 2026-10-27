import unittest
import application as app

class GraphHandoffTests(unittest.TestCase):
    def test_native_stage_preserves_measurement_and_identity_fields(self):
        m=app.module('coherent_stage_contract',app.R01/'validation/coherent_application/integrate.py')
        n=dict(observation_id='owner',receiver=1,native_receiver_id=0,channel=6,time_s=1,actual_rf_hz=12,ignored='private')
        row=m.stage_row(n,123,.03)
        self.assertEqual(row,dict(observation_id='owner',receiver=1,native_receiver_id=0,channel=6,time_s=1,actual_rf_hz=12,measured_cfo_hz=123,fractional_margin=.03))

if __name__=='__main__':unittest.main()
