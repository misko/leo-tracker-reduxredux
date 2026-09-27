import importlib.util
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expanded_proposal_runner',HERE/'run.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def test_selects_all_inactive_receivers_without_reading_reference_labels():
    rows=[{'case_id':'quiet','decisions':[{'active':False},{'active':False}]},
          {'case_id':'mixed','decisions':[{'active':True},{'active':False}]}]
    assert module.targets(rows)==[('quiet',0),('quiet',1),('mixed',1)]
