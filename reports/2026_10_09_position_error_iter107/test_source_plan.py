import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('plan',Path(__file__).with_name('source_plan.py'))
plan=importlib.util.module_from_spec(spec);spec.loader.exec_module(plan)


class SourcePlanTest(unittest.TestCase):
    def test_mismatch_not_missing(self):
        self.assertEqual(plan.compatible({'bank':'one','snapshot':None},{'bank':'two','snapshot':'new'}),['bank'])

    def test_sanitization_excludes_reference_and_selection(self):
        document=dict(session_id='s',input_manifest_sha256='i',analysis_manifest_sha256='a',evidence_sha256='e',configuration={},reference_latitude_deg=1,
                      diagnostics={'bank':{},'checkpoint_binding':'b','reference_errors':[9]},methods=[{'name':'V16','points':[{'east_km':2,'north_km':3,'spacing_km':5,'score':4,'error_km':100}], 'arms':[{'selected':{'error_km':9}}]}])
        value=plan.sanitize(document)
        self.assertNotIn('reference_latitude_deg',value)
        self.assertNotIn('arms',value['methods'][0])
        self.assertNotIn('error_km',value['methods'][0]['points'][0])


if __name__=='__main__':unittest.main()
