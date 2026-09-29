"""Pinned-runtime routing and overlap policy checks (no hardware or storage)."""
import unittest
from types import SimpleNamespace

from leo.scanner.adaptive_hop_analysis import FourRateVariableDwellAnalysisConfigurationV6
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.application.scanner_trajectory import project_scanner_candidates


class RuntimeTests(unittest.TestCase):
    def test_schedule_all_supported_rates_and_durations(self):
        for rate in (2500000,5000000,7500000,10000000):
            for stride,counts in ((120,(1,2,3)),(10,(11,23,35)),(20,(6,12,18))):
                cfg=FourRateVariableDwellAnalysisConfigurationV6(sample_rate_hz=rate,probe_stride_ms=stride)
                self.assertEqual(tuple(cfg.scheduled_probe_count(rate*ms//1000) for ms in (120,240,360)),counts)

    def test_production_projection_removes_odd_dense_probes(self):
        sid="synthetic-density"
        timing=SimpleNamespace(sample_rate_hz=5000000,session_id=sid,
            first_sample_bracket_width_ns=1000,first_sample_estimate_utc_ns=1000000000000000,
            session_start_device_sample_counter=0)
        c=TrackingCandidate(0,10000,0.1,1000.0,0.8,0.1,0.7,True)
        probes=tuple(TrackingProbe(0,rx,index,index*10,1,"upper",10940000000.0,0,0,(c,))
                     for index in range(11) for rx in (0,1))
        source=TrackingInput(sid,"adaptive",5000000,"radio-test","stream-test",
            "sha256:"+"a"*64,"sha256:"+"b"*64,"sha256:"+"c"*64,timing,True,probes)
        output=project_scanner_candidates(source)
        self.assertEqual(len(output),12)
        self.assertEqual({p.probe_index for p in output},{0,2,4,6,8,10})
        self.assertEqual({p.receiver_id for p in output},{0,1})


if __name__ == "__main__":
    unittest.main()
