import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('ungated_pgo',Path(__file__).resolve().parents[3]/'tools/build_ungated_glrt_pgo.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_recipe_preserves_detector_policy_and_pairs_build_paths():
    receipt={'commands':[{'argv':['gcc','-DLEO_DIAG_BYPASS_COARSE=1','-O3','-c','/src/native_glrt.c','-o','/old/objects/native_glrt.c.o']},
                         {'argv':['gcc-ar','rcs','/old/libleo-native-glrt.a','/old/objects/native_glrt.c.o']},
                         {'argv':['gcc','/old/objects/native_glrt_cli.c.o','-o','/old/leo-native-glrt']}]}
    for mode,flag in [('generate','-fprofile-generate'),('use','-fprofile-use')]:
        result=module.recipes(receipt,Path('/new'),mode)
        assert len(result)==2 and flag in result[0]
        assert '-DLEO_DIAG_BYPASS_COARSE=1' in result[0] and '-O3' in result[0]
        assert result[0][-1]=='/new/objects/native_glrt.c.o'
        assert result[1]==['gcc-ar','rcs','/new/libleo-native-glrt.a','/new/objects/native_glrt.c.o']
    with pytest.raises(ValueError):module.recipes(receipt,Path('/new'),'unknown')


def test_unlinked_czt_member_stays_ordinary():
    receipt={'commands':[{'argv':['gcc','-c','/src/conditioned_czt_wrapper.c','-o','/old/objects/czt.o']},
                         {'argv':['gcc-ar','rcs','/old/libleo-native-glrt.a','/old/objects/czt.o']}]}
    for mode in ['generate','use']:
        assert not any('profile' in x for x in module.recipes(receipt,Path('/new'),mode)[0])
