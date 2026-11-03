import sys,unittest
from types import SimpleNamespace
from additional_pipeline import redirected,MAPPING
from benchmark import PROTOCOL


class PipelineTests(unittest.TestCase):
    def test_frozen_mapping(self):
        self.assertEqual(list(MAPPING.values()),PROTOCOL['additional_scans'])

    def test_restores_after_failure(self):
        module=SimpleNamespace(ROOT='original',SESSIONS={'old':'scan'})
        runtime=SimpleNamespace(load_expanded_scan='old_loader');argv=sys.argv
        with self.assertRaises(RuntimeError):
            with redirected(module,runtime,'new',{'A':'additional'},'new_loader',['run']):
                self.assertEqual(module.ROOT,'new');self.assertEqual(runtime.load_expanded_scan,'new_loader')
                raise RuntimeError('deliberate')
        self.assertEqual(module.ROOT,'original');self.assertEqual(module.SESSIONS,{'old':'scan'})
        self.assertEqual(runtime.load_expanded_scan,'old_loader');self.assertIs(sys.argv,argv)
