from collections import Counter
from unittest import TestCase

from reports.ALGO08.v3 import seekable_eight_raw as experiment
from reports.ALGO08.v3 import seekable_member as seek


class EightMillisecondScopeTests(TestCase):
    def test_new_root_schema_does_not_change_default_layout(self):
        self.assertEqual(seek.layout(120_000, None), (seek.SCHEMA, seek.PART_BYTES))
        schema, sizes = seek.layout(80_000, None)
        self.assertNotEqual(schema, seek.SCHEMA)
        self.assertEqual(sizes, (640_000, 960_000))
        with self.assertRaisesRegex(ValueError, "Unknown seekable aperture"):
            seek.layout(100_000, None)

    def test_audited_stereo_short_realizes_one_exact_read_only_prefix(self):
        reads, loads = [], {}

        class Reader:
            def read(self, sequence, *, full):
                reads.append((sequence, full))
                return bytes(seek.WINDOW_BYTES if full else 640_000)

        held = experiment.CommittedSamples(Reader(), 37, loads)
        self.assertEqual(held.shape, (200_000, 2, 2))
        a = held.realize(False)
        self.assertEqual(a.shape, (80_000, 2, 2))
        self.assertFalse(a.flags.writeable)
        self.assertIs(a, held.realize(False))
        self.assertEqual(reads, [(37, False)])
        self.assertEqual(loads, {37: "short_primary"})
        with self.assertRaisesRegex(ValueError, "switch"):
            held.realize(True)

    def test_anchor_requires_the_actual_entire_window(self):
        class Reader:
            read = lambda *args, **kwargs: bytes(seek.WINDOW_BYTES-1)

        with self.assertRaises(ValueError):
            experiment.CommittedSamples(Reader(), 0, Counter()).realize(True)
