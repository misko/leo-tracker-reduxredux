"""Independent frozen-control summaries; never call an RF scorer or use GPS."""

import argparse
import collections
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import time

from baseline_scope import sha
from integration import upper95

HERE=Path(__file__).resolve().parent
TIMING=HERE.parent/'timing'
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
sys.path.insert(0,str(RUNTIME))


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as stream:return json.load(stream)


def write(name,value):
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def timing_module():
    spec=importlib.util.spec_from_file_location('independent_timing_control_geometry',TIMING/'timing_search.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def verify_source():
    protocol=read(TIMING/'protocol.json')
    for path,digest in protocol['files'].items():assert sha(path)==digest,path
    authorization=read(TIMING/'run_authorization.json')
    assert authorization['protocol_sha256']==sha(TIMING/'protocol.json')
    tests=read(TIMING/'test_results.json');assert tests['exit_code']==0
    assert 'test_confirmation_values_do_not_change_selection_receipt' in tests['stderr']
    return protocol


def verify_rows(document,timing):
    assert document['protocol_sha256']==sha(TIMING/'protocol.json')
    rows=document['rows'];assert len({r['target_sha256'] for r in rows})==len(rows)
    selections=0;exposure=0;blocks=0;callback_hashes=[]
    for row in rows:
        r=row['result'];assert r['status']=='complete'
        receipt=r['selection_receipt'];disk=TIMING/'selections'/(r['owner_id'].replace('/','_')+'.json')
        assert read(disk)==receipt
        copy={k:v for k,v in receipt.items() if k!='selection_sha256'}
        assert timing.digest(copy)==receipt['selection_sha256']
        assert receipt['point_selected']==r['point']['selected']
        assert receipt['selected']==r['search']['selected']
        assert receipt['confirmation_accessed'] is False
        callback_hashes.append(sha(disk));selections+=1
        ownership=r['ownership'];intervals=ownership['intervals'];modes=r['mode_provenance']
        for a in intervals:
            for b in intervals:
                if a['group']!=b['group']:assert a['stop']<=b['start'] or b['stop']<=a['start']
        point_zero=[]
        for trial in r['exposure']:
            score=trial['score'];exposure+=1
            assert -256<=score['offset_samples']<=256
            if trial['stage']=='coarse' and score['offset_samples']==0 and score['status']=='complete':point_zero.append(trial)
            geometries=timing.geometry(200000,10000000,score['epoch_samples'],ownership,'search') if score['status']=='complete' else []
            blocks+=len(geometries)
            for g in geometries:
                assert any(i['group']=='search' and i['start']<=g['sample_start']<g['sample_stop']<=i['stop'] for i in intervals)
        assert min(point_zero,key=timing.rank_key)==r['point']['selected']
        for method in ('point','search'):
            item=r[method];c=item['confirmation'];selected=item['selected'];mode=modes[selected['mode_index']]
            for g in timing.geometry(200000,10000000,c['epoch_samples'],ownership,'confirmation'):
                assert any(i['group']=='confirmation' and i['start']<=g['sample_start']<g['sample_stop']<=i['stop'] for i in intervals)
            if c['status']=='complete':
                pilot=c['margin']>=.025;compatible=abs(c['tracking_cfo_hz']-mode['cfo_hz'])<=mode['cfo_half_width_hz']
                assert item['evaluation']['pilot_confirmed']==pilot
                assert item['evaluation']['continuity_compatible']==compatible
                assert item['evaluation']['admitted']==(pilot and compatible)
    return dict(independent_targets=len(rows),durable_selection_artifacts=selections,
        searched_proposals=exposure,whole_bank_search_blocks_verified=blocks,
        selection_callback_artifact_hashes=callback_hashes,
        raw_confirmation_redaction='Owned pre-freeze test changed confirmation-group amplitude/phase; independent mocked call-order and whole-bank geometry tests additionally pass.',
        no_new_RF_calls=True)


def null_summary(rows):
    out={}
    for edge in ('lower','upper'):
        for count in (1,8):
            selected=[r for r in rows if r['edge']==edge and r['modes']==count];n=len(selected)
            stats={}
            for method in ('point','search','union'):
                for flag in ('pilot_confirmed','admitted'):
                    k=sum(any(r['result'][m]['evaluation'][flag] for m in ('point','search'))
                        if method=='union' else r['result'][method]['evaluation'][flag] for r in selected)
                    bound=upper95(k,n)
                    stats[f'{method}_{flag}']=dict(confirmations=k,independent_trials=n,
                        observed_rate=k/n,upper95=bound,practical_pass=n>=32 and k/n<=.05 and bound<=.10,
                        expected_count_upper_at576_RXcells=576*bound)
            out[f'{edge}/{count}modes']=stats
    return out


def signal_summary(rows):
    out={}
    for strength in (-12,-18,-24):
        chosen=[r for r in rows if r['db']==strength]
        if not chosen:continue
        methods={}
        for method in ('point','search'):
            available=[r for r in chosen if r['evaluation'][method]['available']]
            for row in available:
                truth=213456.75+row['true_rate_hz_s']*(.354+.01)
                error=row['result'][method]['confirmation']['tracking_cfo_hz']-truth
                assert abs(error-row['evaluation'][method]['cfo_error_hz'])<1e-8
                epoch=4321.25+(1 if row['true_rate_hz_s']>0 else -1)
                selected_epoch=row['result'][method]['confirmation']['epoch_samples']
                expected=(selected_epoch-epoch+10000000/1500)%(10000000/750)-10000000/1500
                assert abs(expected-row['evaluation'][method]['timing_error_samples'])<1e-8
            n=len(chosen);accurate=sum(r['evaluation'][method]['accurate500'] for r in available)
            admitted=[r for r in available if r['evaluation'][method]['admitted']]
            catastrophic=sum(abs(r['evaluation'][method]['cfo_error_hz'])>1000 for r in admitted)
            methods[method]=dict(trials=n,available=len(available),admitted=len(admitted),
                accurate500=accurate,accurate100=sum(r['evaluation'][method]['accurate100'] for r in available),
                correct_timing2=sum(r['evaluation'][method]['correct_timing'] for r in available),
                admitted_accurate500=sum(r['evaluation'][method]['accurate500'] for r in admitted),
                admitted_errors_over1000=catastrophic,
                strong_screen_pass=n>=20 and accurate/n>=.9 and catastrophic==0,
                mean_absolute_CFO_error_hz=sum(abs(r['evaluation'][method]['cfo_error_hz']) for r in available)/len(available),
                by_forecast={f:dict(trials=sum(r['forecast']==f for r in chosen),
                    admitted=sum(r['forecast']==f for r in admitted),
                    accurate500=sum(r['forecast']==f and r['evaluation'][method]['accurate500'] for r in available))
                    for f in ('zero_rate_fallback','rate_propagated')})
        out[str(strength)]=methods
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=('null','signal','boundary','wrong'));args=parser.parse_args()
    began=time.monotonic();protocol=verify_source();timing=timing_module()
    path=TIMING/'outcomes'/(args.kind+'.json.gz');document=read(path)
    verification=verify_rows(document,timing);rows=document['rows']
    summary=null_summary(rows) if args.kind=='null' else signal_summary(rows) if args.kind in ('signal','boundary') else {
        f'{edge}/{count}modes':{method:dict(trials=sum(r['edge']==edge and r['modes']==count for r in rows),
            pilot_confirmed=sum(r['edge']==edge and r['modes']==count and r['result'][method]['evaluation']['pilot_confirmed'] for r in rows),
            admitted=sum(r['edge']==edge and r['modes']==count and r['result'][method]['evaluation']['admitted'] for r in rows))
            for method in ('point','search')} for edge in ('lower','upper') for count in (1,8)}
    out=dict(kind=args.kind,source_integrity_passed=True,verification=verification,summary=summary,
        protocol_sha256=sha(TIMING/'protocol.json'),outcome_sha256=sha(path),
        fixed_timing_phase_coverage_limited=args.kind in ('signal','boundary'),
        timing_phase_limit='Offsets in signal control lie on/near coarse8sample grid; no worst half-cell (~4sample) coverage claim.',
        synthetic_earlier_CFO_origin_caveat='Earlier scalar is a fabricated evolution intercept, not a separately generated measured midpoint; target truth remains internally consistent.',
        source_or_measurement_errors=[],hard_scientific_decision='see frozen primary search frequency/null screen; boundary/wrong are mechanism diagnostics',
        held_validation_targets_read=False,geography_read=False,new_RF_calls=0,
        seconds=time.monotonic()-began)
    write(args.kind+'_control_audit.json',out)
    print(json.dumps(dict(kind=args.kind,source_integrity_passed=True,verification={k:v for k,v in verification.items() if k!='selection_callback_artifact_hashes'},summary=summary,seconds=out['seconds']),indent=2))


if __name__=='__main__':main()
