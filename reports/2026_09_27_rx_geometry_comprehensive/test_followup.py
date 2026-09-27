"""Portable follow-up evidence checks, without scientific runtime dependencies."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
BASE = HERE / 'followup_sources/2026_09_27_rx_disjoint_confirmation'


class FollowupTests(unittest.TestCase):
    def test_source_hashes(self):
        for entry in json.loads((HERE / 'followup_sources/manifest.json').read_text()):
            path = HERE / 'followup_sources' / entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])

    def test_gate_and_support(self):
        summary = json.loads((BASE / 'summary-v2.json').read_text())
        self.assertFalse(summary['gate']['advance'])
        self.assertEqual([k for k, v in summary['gate']['checks'].items() if not v], ['X_to_Y_three_recordings'])
        self.assertEqual(sum(v['supported_tracks'] for v in summary['support'].values()), 179)
        self.assertEqual(sum(v['unsupported_tracks'] for v in summary['support'].values()), 62)
        for direction, count in [('X_to_Y', 2), ('Y_to_X', 4)]:
            result = summary['results'][direction]
            self.assertEqual(result['normal']['recordings_improving'], count)
            self.assertEqual(result['null']['recordings_improving'], 0)
            self.assertAlmostEqual(sum(result['normal']['per_recording'].values()) / 4,
                                   result['normal']['equal_recording_gain'], places=14)

    def test_source_continuity_recomputed(self):
        spec = importlib.util.spec_from_file_location('archived_source_math', BASE / 'source_continuity_math.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        summary = json.loads((BASE / 'source-audit-summary.json').read_text())
        for filename, sha in summary['source_sha256'].items():
            self.assertEqual(hashlib.sha256((BASE / filename).read_bytes()).hexdigest(), sha)
        raw = json.loads((BASE / 'source-audit-scan-fw-8f4f960d9db67798.json').read_text())
        left, right = raw['tracks']
        saved = summary['results']['scan-fw-8f4f960d9db67798']['cross_channel']
        for key, a, b, n in [('left_to_right', left, right, 14), ('right_to_left', right, left, 16)]:
            recomputed = module.cross_channel_difference(a['rows'], b['rows'])
            self.assertEqual(recomputed, saved[key])
            self.assertEqual(recomputed['points'], n)
            self.assertTrue(math.isfinite(recomputed['difference_rms_after_constant_hz']))
            self.assertLess(recomputed['max_bracket_gap_s'], 1.5)

    def test_figure_bindings(self):
        manifest = json.loads((HERE / 'followup_figure_manifest.json').read_text())
        self.assertEqual(hashlib.sha256((HERE / 'build_followup_figures.py').read_bytes()).hexdigest(), manifest['generator_sha256'])
        self.assertEqual(len(manifest['figure_sha256']), 4)
        for field in ('input_sha256', 'figure_sha256'):
            for filename, sha in manifest[field].items():
                self.assertEqual(hashlib.sha256((HERE / filename).read_bytes()).hexdigest(), sha)


if __name__ == '__main__':
    unittest.main()
