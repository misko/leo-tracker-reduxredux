import importlib.util
from pathlib import Path

from leo.native_pipeline.membership import OBSERVATION_HEADER,SOURCE_HEADER


def test_comparison_ignores_run_id_but_detects_changed_score(tmp_path):
    source=Path(__file__).resolve().parents[3]/'tools/compare_observation_checkpoints.py'
    spec=importlib.util.spec_from_file_location('checkpoint_comparison',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def fixture(name,score):
        path=tmp_path/name;path.mkdir(exist_ok=True)
        row=[name,'group',0,1,'lower',11200000000,100,150,200,-10,score,.1,.3]
        (path/'observations.tsv').write_text('\t'.join(OBSERVATION_HEADER)+'\n'+'\t'.join(map(str,row))+'\n')
        (path/'candidate-map.tsv').write_text('\t'.join(SOURCE_HEADER)+'\n'+f'{name}\tgroup\t0\t0\t0\t0\tinteger\tarm\n')
        return path
    a,b=fixture('run-a',.4),fixture('run-b',.4)
    assert module.compare(a,b)['all_scientific_observations_exact']
    fixture('run-b',.5)
    result=module.compare(a,b)
    assert not result['all_scientific_observations_exact']
    assert result['changed_sources']==[(0,0,0,0)]
