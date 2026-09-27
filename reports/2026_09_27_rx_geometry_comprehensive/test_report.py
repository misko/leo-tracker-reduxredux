"""Portable evidence/figure integrity checks; no RF or database access required."""
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import unittest

HERE = Path(__file__).resolve().parent


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / 'plot_data.json').read_text())

    def test_cohorts_and_finite_values(self):
        self.assertEqual(len(self.data['geographic_rows']), 8)
        self.assertEqual(len({r['session_id'] for r in self.data['geographic_rows']}), 4)
        self.assertEqual(len(self.data['calibration_loso']), 6)
        self.assertEqual(len(self.data['fold_random_effects']), 6)
        self.assertEqual(len(self.data['association_transfer']), 12)
        def check(value):
            if isinstance(value, dict):
                for item in value.values(): check(item)
            elif isinstance(value, list):
                for item in value: check(item)
            elif isinstance(value, (float, int)):
                self.assertTrue(math.isfinite(value))
        check(self.data)

    def test_geographic_means_and_receipts(self):
        expected = {'D': 4.123608415426307, 'old': 3.954376920464574,
                    'mixture': 4.453144248350793, 'dual_shared': 4.1942779679000175}
        for model, value in expected.items():
            self.assertAlmostEqual(sum(r[model] for r in self.data['geographic_rows']) / 8, value, places=9)
        source = json.loads((HERE / 'sources/2026_09_27_roof_balanced_confirmation/dual-shared-geometry-distances.json').read_text())
        rows = {(r['session_id'], r['prior']): r for r in source['rows']}
        for r in self.data['geographic_rows']:
            self.assertEqual(r['dual_shared'], rows[r['session_id'], r['prior']]['errors_km']['dual'])

    def test_source_hashes(self):
        entries = json.loads((HERE / 'sources/manifest.json').read_text())
        for entry in entries:
            path = HERE / 'sources' / entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
        bundled = {'sha256:' + entry['sha256'] for entry in entries}
        self.assertTrue(set(self.data['source_sha256'].values()) <= bundled)

    def test_figures_and_generator_binding(self):
        manifest = json.loads((HERE / 'figure_manifest.json').read_text())
        for key, filename in [('generator_sha256', 'build_figures.py'), ('plot_data_sha256', 'plot_data.json')]:
            self.assertEqual(manifest[key], 'sha256:' + hashlib.sha256((HERE / filename).read_bytes()).hexdigest())
        self.assertEqual(len(manifest['figures']), 16)
        for ext in ('png', 'svg'):
            self.assertEqual(len(list((HERE / 'figures').glob('*.' + ext))), 8)
        for filename in manifest['figures']:
            self.assertGreater((HERE / 'figures' / filename).stat().st_size, 1000)

    def test_portable_report_links(self):
        for filename in ('README.md', 'EXPERIMENT_LOG.md', 'sources/INDEX.md'):
            source = HERE / filename
            for target in re.findall(r'\]\(([^)]+)\)', source.read_text()):
                if '://' in target or target.startswith('#'):
                    continue
                path = (source.parent / target.split('#')[0]).resolve()
                if path.exists():
                    continue
                # Sparse worktrees can omit related reports already on main.
                root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=HERE, text=True).strip())
                relative = path.relative_to(root)
                result = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + str(relative)], cwd=root, capture_output=True)
                self.assertEqual(result.returncode, 0, f'{filename}: missing {target}')


if __name__ == '__main__':
    unittest.main()
