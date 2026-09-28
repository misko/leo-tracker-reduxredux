"""Score completed approximate-search cohorts against original individual hits."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

SOURCE=Path(__file__).resolve().parent.parent/'2026_09_28_arm_full_optimization/independent_summary.py'
spec=importlib.util.spec_from_file_location('frozen_independent',SOURCE)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def load_native(path, selected):
    expected={(c['session_id'],c['visit_index']):c for c in selected}
    result={}
    records=[json.loads(line) for line in path.read_text().splitlines()]
    if path.name=='raw.jsonl':
        grouped={}
        for raw in records:
            c=raw['context'];key=(c['session_id'],c['visit_index'])
            item=grouped.setdefault(key,dict(context=c,returncode=0,stderr='',rows=[]))
            if item['context']!=c:raise ValueError('ARM window context differs')
            item['rows'].append(raw['native'])
        records=list(grouped.values())
    for record in records:
        context=record['context']
        case=(context['session_id'],context['visit_index'])
        if case not in expected or case in result:
            raise ValueError('unexpected or duplicate dwell')
        if context['sha256']!=expected[case]['sha256']:
            raise ValueError('input hash differs')
        if record['returncode']!=0 or record['stderr']:
            raise ValueError('native execution failed')
        windows={}
        for row in record['rows']:
            key=(row['receiver_id'],row['probe_index'])
            if key in windows or key not in audit.WINDOW_KEYS:
                raise ValueError('unexpected or duplicate window')
            if row['candidate_count']!=len(row['candidates']) or not 0<=row['candidate_count']<=8:
                raise ValueError('candidate inventory differs')
            for c in row['candidates']:
                if c.get('glrt_complete')!=1:
                    raise ValueError('candidate GLRT incomplete')
                for field in ('epoch','acquired_cfo_hz','tracking_cfo_hz','exact_score','control_score','margin'):
                    if not math.isfinite(c[field]):
                        raise ValueError('nonfinite candidate')
            windows[key]=row
        if windows.keys()!=audit.WINDOW_KEYS:
            raise ValueError('missing windows')
        result[case]=windows
    if result.keys()!=expected.keys():
        raise ValueError('missing dwells')
    return result


def score(folder, baseline, exclude_cohort=None):
    manifest=json.loads((folder/'manifest.json').read_text())
    selected=manifest['selected']
    if not manifest['complete'] or manifest['processed_dwells']!=len(selected):
        raise ValueError('incomplete manifest')
    if len({(c['session_id'],c['visit_index']) for c in selected})!=len(selected):
        raise ValueError('duplicate selected dwell')
    native_path=folder/('raw.jsonl' if 'raw_sha256' in manifest else 'rows.jsonl')
    if 'raw_sha256' in manifest and audit.sha256(native_path)!=manifest['raw_sha256']:
        raise ValueError('ARM raw hash differs from completed manifest')
    native=load_native(native_path,selected)
    excluded=0
    if exclude_cohort is not None:
        excluded_manifest=json.loads((exclude_cohort/'manifest.json').read_text())
        if not excluded_manifest['complete']:
            raise ValueError('excluded cohort incomplete')
        exclude={(c['session_id'],c['visit_index']):c for c in excluded_manifest['selected']}
        contexts={(c['session_id'],c['visit_index']):c for c in selected}
        if not exclude.keys()<=contexts.keys() or any(exclude[k]['sha256']!=contexts[k]['sha256'] for k in exclude):
            raise ValueError('excluded cohort is not a matching subset')
        selected=[c for c in selected if (c['session_id'],c['visit_index']) not in exclude]
        native={k:v for k,v in native.items() if k not in exclude}
        excluded=len(exclude)
    result=audit.summarize(selected,audit.load_baseline(baseline),native)
    for c in [result['totals'],*result['by_rate'].values()]:
        c['baseline_candidate_slots']=c.pop('candidates')
        c['actual_candidate_glrts']=0
        c['unmatched_positive_hits']=c['native_positive_hits']-c['recovered_positive_hits']
        c['hit_recovery_fraction']=c['recovered_positive_hits']/c['reference_positive_hits'] if c['reference_positive_hits'] else None
    for context in selected:
        windows=native[(context['session_id'],context['visit_index'])]
        calls=sum(len(w['candidates']) for w in windows.values())
        result['totals']['actual_candidate_glrts']+=calls
        result['by_rate'][str(context['rate_hz'])]['actual_candidate_glrts']+=calls
    result.update(schema='sparse-proposal-individual-hit-audit/v1',
        scope='Measured final GLRT hits; one-to-one matching within same20ms window, <=2samples and <=8kHz',
        positive_margin_gate=.025,excluded_dwells=excluded,baseline_sha256=audit.sha256(baseline),
        native_sha256=audit.sha256(native_path),manifest_sha256=audit.sha256(folder/'manifest.json'),
        matcher_source_sha256=audit.sha256(SOURCE))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=Path('reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exclude-cohort',type=Path)
    args=parser.parse_args();result=score(args.cohort,args.baseline,args.exclude_cohort)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['totals'],indent=2))
