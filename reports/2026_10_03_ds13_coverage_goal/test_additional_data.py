import tempfile,unittest
from pathlib import Path
from additional_data import verify_artifacts,load_additional
from benchmark import digest


class AdditionalDataTests(unittest.TestCase):
    def test_digest_guard(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            for file in ('expanded.npz','observations.npz'):(directory/file).write_bytes(b'fixture')
            receipt={'artifacts':{file:digest(directory/file) for file in ('expanded.npz','observations.npz')}}
            verify_artifacts(directory,receipt)
            (directory/'observations.npz').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_artifacts(directory,receipt)

    def test_unfrozen_session_rejected(self):
        with self.assertRaises(ValueError):load_additional('not-frozen')
