"""Audit completed inference, publish compact receipts and raw hashes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import evaluate as e


def compact_fit(row):
    if row is None:return None
    keep=('arm','start','status','qualified','x','latlon','error_m','objective','rms_hz','reference',
          'phase_closed','optimizer_success','all_gates_pass','mixture_phase_interior','active_points',
          'seconds','lost_ids','added_ids','reassigned_ids','unexpected_reassigned_ids','parameters',
          'owners_sha256','native_ids_sha256','reason')
    out={k:row[k] for k in keep if k in row}
    for key in ('lost_ids','added_ids','reassigned_ids','unexpected_reassigned_ids'):
        if key in out:
            values=out.pop(key);out[key+'_count']=len(values)
            out[key+'_sha256']=hashlib.sha256(json.dumps(sorted(values)).encode()).hexdigest()
    failed=row.get('failed_gates',{})
    out['failed_gates_count']=len(failed);out['first_failed_gates']=dict(list(failed.items())[:8])
    return out


def main():
    protocol=e.read(e.OUT/'protocol.json');cases=[r['case'] for r in protocol['cohort']]
    missing=[c for c in cases if not (e.OUT/c/'result.json').exists()]
    if missing:raise RuntimeError('Incomplete cases: '+','.join(missing))
    checks=[];raw={};histories=[];receipts=e.OUT/'receipts';receipts.mkdir(exist_ok=True)
    for entry in protocol['cohort']:
        case=entry['case'];folder=e.OUT/case;result=e.read(folder/'result.json')
        for path,digest in entry['sources'].items():
            if e.sha(path)!=digest:raise ValueError('Source changed: '+path)
        baseline=result['baseline']
        for method,values in result['methods'].items():
            for a in e.ARMS:
                if values['final'][a]['associated']!=baseline[a]['associated']:raise ValueError('Coverage changed')
                if values['selected'] is None and values['final'][a]!=baseline[a]:raise ValueError('Fallback differs')
            if values['selected']:
                candidates=result['history_records'] if values['selected']=='complete_history' else result['records'][method]
                chosen=next(r for r in candidates if r['name']==values['selected'])
                if not chosen['accepted'] or not all(g>0 for g in chosen['gains'].values()):raise ValueError('Invalid acceptance')
                for a in e.ARMS:
                    r=chosen['pair'][a]
                    if not (r['qualified'] and r['all_gates_pass'] and r['phase_closed'] and r['optimizer_success'] and r['mixture_phase_interior']):raise ValueError('Unqualified accepted result')
                    if r['lost_ids'] or r['unexpected_reassigned_ids']:raise ValueError('Owners lost or unexpected relabeling')
                    if 'control' in chosen and r['native_ids_sha256']!=chosen['control'][a]['native_ids_sha256']:raise ValueError('Native fit evidence differs')
        records={}
        for method,items in result['records'].items():
            records[method]=[]
            for item in items:
                r={k:v for k,v in item.items() if k not in ('pair','control')}
                for key in ('pair','control'):
                    if key in item:r[key]={a:compact_fit(v) for a,v in item[key].items()}
                records[method].append(r)
        compact=dict(case=case,baseline=baseline,methods=result['methods'],history=result['history'],targets=result['targets'],
                     execution_status=result.get('execution_status','complete'),
                     failures=result['failures'],seconds=result['seconds'],records=records,replay=e.read(folder/'replay.json'),
                     history_records=[dict(name=r['name'],gains=r['gains'],accepted=r['accepted'],pair={a:compact_fit(v) for a,v in r['pair'].items()}) for r in result['history_records']])
        e.write(receipts/(case+'.json'),compact)
        for path in folder.rglob('*.json'):
            raw[str(path.relative_to(e.OUT))]=e.sha(path)
        z=e.read(e.ROOTS[case[:4]]/'inputs'/(case+'.json'))
        observations=Path(z['native_path'])/'observations.json'
        checks.append(dict(case=case,observations_sha256=e.sha(observations),native_path=str(observations),
                           baseline_owners_sha256=hashlib.sha256(json.dumps(z['baseline_owners'],sort_keys=True).encode()).hexdigest(),
                           catalogue_sha256=e.sha(e.ROOTS[case[:4]]/'catalogues'/(case+'.json'))))
        for path in folder.rglob('export.json'):
            export=e.read(path);request=export['request'];cutoff=request['cutoff']
            for n,r in export['export']['chosen'].items():
                assert request['latest'][n]-r['epoch_utc_ns']>=1e9
                assert cutoff-int(72*3.6e12)<=r['collected_utc_ns']<=cutoff
                histories.append(dict(case=case,norad=int(n),epoch=r['epoch_utc_ns'],collected=r['collected_utc_ns'],cutoff=cutoff,
                    nominal_epoch=request['latest'][n],element_sha256=hashlib.sha256('\n'.join(r['lines']).encode()).hexdigest()))
    code=list(e.OUT.glob('*.py'))+[e.PRIOR/'reconsider.py',e.PRIOR/'read_history.py',e.PRIOR/'transfer.py',
        e.OUT.parent/'2026_11_01_ds26_ten_solutions/experiment.py',e.OUT.parent/'2026_11_01_ds26_solution_prototypes/prototype.py']
    e.write(e.OUT/'manifest.json',dict(sealed_utc_ns=time.time_ns(),base_revision=protocol['base_revision'],current_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=e.REPO,text=True).strip(),
        raw_archive_root=str(e.OUT),raw_json_sha256=raw,source_sha256={str(p):e.sha(p) for p in code},checks=checks,causal_history_exports=histories,
        implementation_notes=['ALGO06 accepted mixtures restored before comparison','All shared conditional attachments retained',
            'Gradient-only trigger optimization removes unused omission Hessians; exact ranking equality tested; early workers used original arithmetic',
            '10 initial evaluation workers plus2 validation workers; later3 tail-roster and3 DS27 workers use freed capacity and per-case locks; waiting duplicates do not refit; single-thread numerical libraries'],
        scope='Frozen downstream conditional reassociation evaluation; not fresh IQ/GLRT/regional acquisition; no production writes',
        validation='All completed outcomes checked for exact fallback, fixed coverage, positive paired RF gain, gates, owner retention and native IDs'))
    print('Sealed',len(cases),'scans;',len(raw),'raw artifacts;',len(histories),'causal history records')


if __name__=='__main__':main()
