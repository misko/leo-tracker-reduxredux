import unittest
from unittest.mock import patch
from pathlib import Path
from run_batch import command,run


class BatchTests(unittest.TestCase):
    def test_variant_shares_refinement_but_versions_model(self):
        directory=Path('/tmp/N02')
        self.assertIn('/tmp/N02/observations.json',command('refine',directory,'seed-timing-v6'))
        self.assertIn('/tmp/N02/seed-timing-v6',command('calibrate',directory,'seed-timing-v6'))
        self.assertIn('/tmp/N02',command('seed',directory,'seed-timing-v6'))
        self.assertTrue(command('plot',directory,'seed-timing-v6')[-1].endswith('pilot-N02-seeded'))

    def test_variant_cannot_escape_scan_directory(self):
        with self.assertRaisesRegex(ValueError,'variant'):
            run(Path('/tmp'),['N02'],['calibrate'],variant='../other')

    def test_numerical_screens_route_to_same_development_scan(self):
        for stage in ('prior','curvature'):
            args=command(stage,Path('/bulk/inputs/N11'),'seed-timing-v6')
            self.assertEqual(args[-3:],['/bulk/inputs','--label','N11'])
        self.assertIn('/bulk/inputs/N11/seed-timing-v6',command('position',Path('/bulk/inputs/N11'),'seed-timing-v6'))

    def test_screen_cannot_use_validation_scan(self):
        with self.assertRaisesRegex(ValueError,'development'):
            run(Path('/tmp'),['N04'],['prior'],variant='seed-timing-v6')

    def test_refinement_is_existing_data_only(self):
        args=command('refine',Path('/tmp/scan'))
        self.assertTrue(args[1].endswith('run_refinement.py'))
        self.assertIn('/tmp/scan/observations.json',args)
        self.assertNotIn('capture',args)

    def test_bounded_scan_count(self):
        with self.assertRaisesRegex(ValueError,'bounded'):
            run(Path('/tmp'),['A','B','N01','N02','N03'],['refine'])

    def test_locked_test_analysis_not_unblinded(self):
        with patch('run_batch.Path.exists',return_value=False):
            with self.assertRaisesRegex(ValueError,'locked-test'):
                run(Path('/tmp'),['N01'],['calibrate'])
