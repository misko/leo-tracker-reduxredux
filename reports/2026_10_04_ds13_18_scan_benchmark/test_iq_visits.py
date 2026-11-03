import unittest
from types import SimpleNamespace as NS
from iq_visits import read_event, visit_ordinals


class VisitsTests(unittest.TestCase):
    def test_gap_maps_event_to_retained_ordinal(self):
        visits = [NS(event=NS(visit_index=i)) for i in (0, 2, 3)]
        published = NS(manifest=NS(receipt=NS(visits=visits)))
        self.assertEqual(visit_ordinals(published.manifest.receipt), {0: 0, 2: 1, 3: 2})
        calls = []
        def read(pub, ordinal):
            calls.append(ordinal)
            return visits[ordinal], 'iq'
        self.assertEqual(read_event(NS(read_visit_ci16=read), published, 3)[1], 'iq')
        self.assertEqual(calls, [2])

    def test_missing_event_does_not_read_neighbor(self):
        published = NS(manifest=NS(receipt=NS(visits=[NS(event=NS(visit_index=2))])))
        with self.assertRaises(LookupError):
            read_event(None, published, 1)

    def test_duplicate_event_fails(self):
        with self.assertRaises(ValueError):
            visit_ordinals(NS(visits=[NS(event=NS(visit_index=2))]*2))


if __name__ == '__main__':
    unittest.main()
