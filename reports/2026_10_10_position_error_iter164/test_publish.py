"""Pure presentation fixtures; optional rendering uses synthetic values only."""
import importlib.util
from pathlib import Path

import pytest


def load(name):
    spec=importlib.util.spec_from_file_location(name+'_164_test',Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


P=load('publish');M=load('report_metrics')


def fixture():
    members=[];rows=[]
    for dataset,count in M.COUNTS.items():
        for i in range(count):
            label=f'{dataset}-{i:03}';members.append(dict(label=label,dataset=dataset))
            rows.append(dict(label=label,dataset=dataset,statuses={p:'complete' for p in ('search','native','zero')},
                phase_elapsed_s={'search':10.,'native':None,'zero':20.},
                arms={a:{b:dict(status='selected',qualified=True,error_km=float(i)/10,
                               selection={'accepted_stage':'B7'},frequency={}) for b in M.BRANCHES} for a in M.ARMS}))
    return dict(all_terminal=True,rows=rows),members


def test_markdown_all193_coverage_missing_means_and_cost():
    summary,members=fixture()
    item=summary['rows'][0]['arms']['fitted-c']['zero']
    item.pop('error_km');item.update(evaluation_status='failed',evaluation_error='evaluation unavailable')
    metrics=M.aggregate(members,summary['rows']);text=P.markdown(summary,metrics)
    assert 'Available paired subset only' in text and 'withheld' in text
    assert 'evaluation unavailable' in text and '30.0000; ["native"]' in text
    assert all(m['label'] in text for m in members)
    assert 'unavailable: no recorded attempts' in text
    assert '0/3 recorded; 3 unavailable' in text
    assert metrics['coverage'][0]['endpoints']['zero/fitted-c']['evaluation_status']=='failed'
    assert 'Matched c comparison' in text and 'Frequency fit, separately' in text


def test_unsealed_or_foreign_metrics_rejected():
    summary,members=fixture();metrics=M.aggregate(members,summary['rows'])
    summary['all_terminal']=False
    with pytest.raises(ValueError,match='sealed'):P.markdown(summary,metrics)
    summary['all_terminal']=True;metrics['coverage'][0]['label']='foreign'
    with pytest.raises(ValueError,match='coverage'):P.markdown(summary,metrics)


def test_invalid_cost_not_coerced_to_zero():
    summary,members=fixture();summary['rows'][0]['phase_elapsed_s']['native']=float('nan')
    with pytest.raises(ValueError,match='duration'):
        P.markdown(summary,M.aggregate(members,summary['rows']))


def test_static_plots_render_full_tail_zero_and_missing(tmp_path):
    summary,members=fixture()
    summary['rows'][0]['arms']['fitted-c']['zero']['error_km']=300.
    summary['rows'][1]['arms']['zero-c']['native'].pop('error_km')
    metrics=M.aggregate(members,summary['rows'])
    paths=P.publish(summary,metrics,tmp_path)
    assert {p.name for p in paths}=={'paired-position.png','error-ecdf.png','member-errors.png','c-contrast.png'}
    assert all(p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and p.stat().st_size>1000 for p in paths)
    assert (tmp_path/'RESULTS.md').exists() and (tmp_path/'METRICS.json').exists()
