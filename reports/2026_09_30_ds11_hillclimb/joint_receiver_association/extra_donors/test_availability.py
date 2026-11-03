import unittest
from availability_policy import available,orbit_available


class AvailabilityTests(unittest.TestCase):
    def test_analysis_completion_is_required(self):
        self.assertTrue(available(10,12,20,30))
        self.assertFalse(available(10,12,30,30))
        self.assertFalse(available(10,12,9,30))
        self.assertFalse(available(10,31,20,30))

    def test_request_guard_does_not_prove_file_availability(self):
        start=10**12;request=start-506_000_000_000
        self.assertTrue(orbit_available(request,request+10**9,start))
        self.assertFalse(orbit_available(request,start,start))
        self.assertFalse(orbit_available(request,request-1,start))
        self.assertFalse(orbit_available(start-505_000_000_000,start-1,start))
