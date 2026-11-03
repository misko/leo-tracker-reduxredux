import unittest
from training_calibration import seed_catalogs,validate_resume


class TrainingCalibrationTests(unittest.TestCase):
    def test_abstaining_bootstrap_has_no_seed_catalogs(self):
        self.assertEqual(seed_catalogs(dict(modes=[[],[]],proposals=[])),[])

    def test_resume_rejects_changed_training_provenance(self):
        previous=dict(scan='A',fold=0,catalog_numbers=[1,2],source_sha256='old')
        validate_resume(previous,'A',0,[1,2],'old')
        with self.assertRaises(ValueError):validate_resume(previous,'A',0,[1,2],'changed')
        with self.assertRaises(ValueError):validate_resume(previous,'A',1,[1,2],'old')

    def test_shared_candidates_selected_from_training_offset_support(self):
        b={'modes':[[{'offset_hz':1000}],[{'offset_hz':9000}]],'proposals':[
            {'catalog_number':1,'receiver':0,'offset_hz':1100},
            {'catalog_number':2,'receiver':1,'offset_hz':8900},
            {'catalog_number':3,'receiver':0,'offset_hz':9000}]}
        self.assertEqual(seed_catalogs(b),[1,2])


if __name__=='__main__':unittest.main()
