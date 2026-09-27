import hashlib
import unittest

import numpy as np

from known_state import NativeKnownState
from known_state_v2 import NativeKnownStateV2
from test_known_state import CFO, EPOCH, RATE, synthetic


class KnownStateV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1 = NativeKnownState(RATE, "lower")
        cls.v2 = NativeKnownStateV2(RATE, "lower")

    @classmethod
    def tearDownClass(cls):
        cls.v1.close()
        cls.v2.close()

    def test_full_aperture_is_numerically_identical_to_v1(self):
        iq = synthetic()
        for epoch in (EPOCH, EPOCH + 0.35, RATE / 750 - 0.2):
            with self.subTest(epoch=epoch):
                v1 = self.v1.measure(iq, epoch, CFO)
                v2 = self.v2.measure(iq, epoch, CFO)
                for key in ("epoch_samples", "tracking_cfo_hz", "exact_score", "control_score"):
                    self.assertEqual(v2[key], v1[key])

    def test_natural_dual_receiver_stride_needs_no_python_copy(self):
        packed = synthetic()
        dual = np.empty((len(packed), 2, 2), dtype=np.int16)
        dual[:, 0, :] = packed
        dual[:, 1, :] = -packed
        view = dual[:, 0, :]
        self.assertFalse(view.flags.c_contiguous)
        before = hashlib.sha256(dual).digest()
        direct = self.v2.measure(packed, EPOCH + 0.35, CFO)
        strided = self.v2.measure(view, EPOCH + 0.35, CFO)
        self.assertEqual(hashlib.sha256(dual).digest(), before)
        self.assertEqual(strided["sample_stride_i16"], 4)
        self.assertEqual(strided["exact_score"], direct["exact_score"])
        self.assertEqual(strided["control_score"], direct["control_score"])

    def test_partial_support_is_explicit_and_bounded(self):
        result = self.v2.measure(synthetic(), EPOCH + 0.35, CFO, frame_limit=2)
        self.assertEqual(result["support_frames"], 2)
        self.assertGreater(result["available_support_frames"], 10)
        self.assertEqual(result["score_semantics"], "partial_2_frame_final_glrt_unqualified")
        self.assertLess(result["converted_samples"], RATE // 50)
        self.assertGreater(result["margin"], 0.025)

    def test_partial_support_noise_and_tone_controls_do_not_gate(self):
        for frame_limit in (2, 4):
            for kind in ("noise", "tone"):
                with self.subTest(frame_limit=frame_limit, kind=kind):
                    result = self.v2.measure(
                        synthetic(kind), EPOCH + 0.35, CFO, frame_limit=frame_limit
                    )
                    self.assertLessEqual(result["margin"], 0.025)


if __name__ == "__main__":
    unittest.main()
