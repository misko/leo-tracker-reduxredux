"""Response blindness and deterministic bounded whole-prior selection."""
from types import SimpleNamespace
import unittest
import numpy as np
from metadata import observation_metadata, cap_bank
from leo.analysis.regional_position_score import observer
from leo.contracts.regional_position import RegionalPrior, PositionOrbitBank


class PoisonRow(dict):
    def __getitem__(self, key):
        if key in {'measured_cfo_hz', 'measured_hz', 'margin', 'original_associated',
            'original_satellite_number', 'configured_station_reference', 'latitude_deg', 'longitude_deg'}:
            raise AssertionError('Forbidden response/reference read')
        return super().__getitem__(key)


class MetadataTests(unittest.TestCase):
    def test_all_cfo_and_station_fields_are_unread_even_if_poisoned(self):
        rows = [PoisonRow(observation_id=f'row{i}', time_s=30.*i, actual_rf_hz=10.7e9+i*1e8,
            receiver=1+i%2, channel=i+1, measured_cfo_hz=object(),
            configured_station_reference=object()) for i in range(4)]
        obs, projected = observation_metadata(rows)
        np.testing.assert_array_equal(obs.measured_hz, np.zeros(4))
        np.testing.assert_array_equal(obs.margin, np.ones(4))
        self.assertTrue(all('measured_cfo_hz' not in row for row in projected))
        np.testing.assert_array_equal(obs.rf_hz, [r['actual_rf_hz'] for r in rows])

    def test_all_response_perturbations_leave_metadata_identical(self):
        rows = [dict(observation_id=f'row{i}', time_s=float(i), actual_rf_hz=11e9,
            receiver=1, channel=1, measured_cfo_hz=float(i)) for i in range(3)]
        a, pa = observation_metadata(rows)
        for row in rows:
            row['measured_cfo_hz'] = -123456789.
            row['configured_station_reference'] = dict(latitude_deg=-80., longitude_deg=150.)
        b, pb = observation_metadata(rows)
        self.assertEqual(pa, pb)
        for name in ['times_s', 'rf_hz', 'receiver', 'channel', 'measured_hz']:
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name))

    def test_geometric_cap_is_deterministic_and_order_independent(self):
        prior = RegionalPrior()
        site, up = observer(prior, [0., 0.])
        position = np.stack([np.broadcast_to(site+(500.+k)*up, (3, 3)) for k in range(4)])
        bank = PositionOrbitBank([14, 11, 13, 12], [0., 1., 2.], position, np.zeros_like(position))
        selected, receipt = cap_bank(bank, prior, maximum_candidates=2)
        changed, other = cap_bank(bank.select([3, 1, 0, 2]), prior, maximum_candidates=2)
        np.testing.assert_array_equal(selected.numbers, changed.numbers)
        np.testing.assert_array_equal(selected.numbers, [12, 13])
        self.assertEqual(len(receipt['cap_excluded_numbers']), 2)
        self.assertEqual(receipt['retained_after_cap'], 2)


if __name__ == '__main__':
    unittest.main()
