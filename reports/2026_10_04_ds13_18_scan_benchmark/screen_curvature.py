"""Frozen known-roof curvature exclusion, shared across matched RF arms.

Exclude a satellite when any fitted-c baseline receiver track has pooled
(RMS+linear)/(RMS+quadratic) above the cutoff. All other satellite hypotheses
remain available for replacement. This is an in-sample oracle diagnostic,
not a blind association filter and not validation of an orbital correction.
"""
import argparse
import json
from pathlib import Path

from association_search import Search,Settings
from cohort import digest
from discovery import ARMS
from numeric_data import load
from select_associations import run as baseline_selection
from screen_hyperparameters import metrics

HERE=Path(__file__).resolve().parent


def exclusions(rows,cutoff):
    if cutoff<=1:
        raise ValueError('curvature ratio cutoff must exceed one')
    return sorted({r['satellite'] for r in rows if r['arm']=='fitted-c'
                   and r['curvature_ratio'] is not None and r['curvature_ratio']>cutoff})


def allowed_cutoffs(cohort,label,protocol=None):
    split=next((r['split'] for r in cohort['scans'] if r['label']==label),None)
    if split=='development':return (1.1,1.05)
    if split=='validation' and protocol and label in protocol['validation_scans']:
        return tuple(protocol['curvature_cutoffs'])
    raise ValueError('curvature screening requires development or explicitly registered validation')


def run(inputs,label,protocol_path=None):
    cohort=json.loads((HERE/'cohort-v2.json').read_text())
    protocol=json.loads(protocol_path.read_text()) if protocol_path else None
    if protocol and protocol['cohort_sha256']!=digest((HERE/'cohort-v2.json').read_bytes()):
        raise ValueError('validation protocol cohort changed')
    cutoffs=allowed_cutoffs(cohort,label,protocol)
    directory=inputs/label/'seed-timing-v6'
    baseline=baseline_selection(directory)
    diagnostics=HERE/f'pilot-{label}-seeded/alternatives-diagnostics.json'
    diagnostic=json.loads(diagnostics.read_text())
    if diagnostic['source_sha256']!=digest(baseline.read_bytes()):
        raise ValueError('curvature statistics do not bind current baseline')
    for path,expected in diagnostic['sources'].items():
        if digest(Path(path).read_bytes())!=expected:
            raise ValueError('curvature source changed')
    data=load(directory,top_only=False)
    pool_path=directory/'discovery/candidate-pool.json'
    pool=json.loads(pool_path.read_text())
    output=HERE/'curvature-screen'
    output.mkdir(exist_ok=True)
    summary=[]
    for cutoff in cutoffs:
        excluded=exclusions(diagnostic['rows'],cutoff)
        signature=dict(pool=digest(pool_path.read_bytes()),diagnostics=digest(diagnostics.read_bytes()),
                       implementation=digest(Path(__file__).read_bytes()),cutoff=cutoff,excluded_satellites=excluded)
        target=directory/f'selection-curvature-{cutoff:g}.json'
        if target.exists():
            result=json.loads(target.read_text())
            if result['signature']!=signature:
                raise ValueError('curvature selection signature mismatch')
        else:
            arms={}
            for arm in ARMS:
                modes=[m for m in pool['arms'][arm] if m['catalog_number'] not in excluded]
                # Preserve original pool mode indexes for downstream orbit plots.
                indices=[i for i,m in enumerate(pool['arms'][arm]) if m['catalog_number'] not in excluded]
                arms[arm]={}
                for method,allowed,passes in (('greedy',data.top_mask,0),('replacement',data.top_mask,3),('alternatives',None,3)):
                    value=Search(modes,data.group,data.times,data.receiver,data.channel,settings=Settings(),allowed=allowed).run(passes)
                    for stage in ('initial','final'):
                        for assigned in value[stage]['assignments']:
                            assigned['original_row_index']=int(data.original_rows[assigned['row_index']])
                            assigned['mode_index']=indices[assigned['mode_index']]
                        for selected in value[stage]['selected']:
                            selected['mode_index']=indices[selected['mode_index']]
                    arms[arm][method]=value
                    print('CURVATURE',label,cutoff,arm,method,value['final']['assigned'],flush=True)
            result=dict(signature=signature,arms=arms,scope=__doc__,calibration_warnings=pool['signature'].get('calibration_warnings',[]))
            with target.open('x') as stream:
                json.dump(result,stream,allow_nan=False)
        for arm in ARMS:
            for method,value in result['arms'][arm].items():
                summary.append(dict(scan=label,cutoff=cutoff,arm=arm,method=method,excluded_satellites=excluded,
                                    **metrics(value['final'])))
    (output/f'{label}.json').write_text(json.dumps(dict(scope=__doc__,rows=summary),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);p.add_argument('--label',required=True)
    p.add_argument('--validation-protocol',type=Path)
    a=p.parse_args();run(a.inputs,a.label,a.validation_protocol)
