"""Receipt-only DS26 phase-blocker census; no GPS or inference decisions."""
from pathlib import Path
import json, hashlib, csv, random
from collections import Counter

SOURCE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030')
OUT = Path(__file__).resolve().parent

def run():
    hashes = {}
    def read(path):
        b = path.read_bytes(); hashes[str(path)] = hashlib.sha256(b).hexdigest()
        return json.loads(b)
    rows = []
    manifest = read(SOURCE/'candidate-final-inventory.json')
    for case in manifest['rows']:
        if case['dataset'] != 'DS26' or case['state'] != 'complete':continue
        terminal_path = Path(case['terminal_path'])
        terminal = read(terminal_path)
        for attempt in terminal.get('attempts', []):
            path = terminal_path.parent/'recovery'/attempt['track_id']/'annotation/result.json'
            if not path.exists():continue
            annotation = read(path); checks=[]
            score_name = annotation.get('identity_score_name', 'joint')
            for fold in annotation['folds']:
                for arm in ('c0', 'fitted_c'):
                    offers=sorted(fold.get('proposals', []), key=lambda p:p['arms'][arm]['scores'][score_name]['negative_twice_log_density'])
                    if len(offers)<2:continue
                    p=offers[0]; r=p['arms'][arm];check=r.get('phase_reference_check', {})
                    if not check and r.get('history'):check=r['history'][-1]
                    checks.append(dict(seed=fold['seed'],arm=arm,norad=p['norad'],
                        rms_hz=r['scores']['target']['rms_hz'],elevation_deg=r['minimum_target_elevation_deg'],
                        phase_change_s=r['final_phase_change_s'],overflow_s=check.get('maximum_phase_overflow_s',0),
                        margin=offers[1]['arms'][arm]['scores'][score_name]['negative_twice_log_density']-r['scores'][score_name]['negative_twice_log_density']))
            if not checks:continue
            consensus=len({c['norad'] for c in checks})==1
            other_pass=len(checks)==6 and consensus and all(c['rms_hz']<=450 and c['elevation_deg']>=0 and c['margin']>=10 for c in checks)
            phase_fail=any(c['phase_change_s']>.01 for c in checks)
            clipped=any(c['overflow_s']>0 for c in checks)
            rows.append(dict(case=case['case'],track_id=attempt['track_id'],points=attempt['points'],
                status=attempt['status'],norad=checks[0]['norad'] if consensus else None,
                consensus=consensus,other_identity_checks_pass=other_pass,phase_failure=phase_fail,
                clipping=clipped,phase_only_blocked=other_pass and phase_fail,
                maximum_phase_change_s=max(c['phase_change_s'] for c in checks),
                maximum_overflow_s=max(c['overflow_s'] for c in checks),
                source=str(path),terminal=str(terminal_path),checks=checks))
    # Freeze an independent scan-level panel without using position errors.
    blocked={}
    controls={}
    for r in sorted(rows,key=lambda r:(r['case'],-r['points'],r['track_id'])):
        if r['phase_only_blocked'] and r['clipping'] and r['case']!='DS26-0265':blocked.setdefault(r['case'],r)
        if r['status']=='RF_qualified' and not r['phase_failure']:controls.setdefault(r['case'],r)
    controls={k:v for k,v in controls.items() if k not in blocked and k!='DS26-0265'}
    rng=random.Random(20261031)
    panel=[dict(blocked[k],panel_role='clipped_phase') for k in rng.sample(sorted(blocked),min(3,len(blocked)))]
    panel += [dict(controls[k],panel_role='qualified_control') for k in rng.sample(sorted(controls),min(3,len(controls)))]
    summary=dict(assessed_annotations=len(rows),assessed_scans=len({r['case'] for r in rows}),
        phase_failed_annotations=sum(r['phase_failure'] for r in rows),
        clipped_annotations=sum(r['clipping'] for r in rows),
        phase_only_blocked_annotations=sum(r['phase_only_blocked'] for r in rows),
        phase_only_clipped_annotations=sum(r['phase_only_blocked'] and r['clipping'] for r in rows),
        phase_only_clipped_scans=len({r['case'] for r in rows if r['phase_only_blocked'] and r['clipping']}),
        states=dict(Counter(r['status'] for r in rows)),
        interpretation='Recorded winning-fold diagnostics only; not a count of recoverable tracks or new accepted associations')
    result=dict(summary=summary,rows=rows,source_sha256=hashes,GPS_used=False,production_changed=False)
    (OUT/'phase-cohort-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'phase-validation-panel.json').write_text(json.dumps(dict(seed=20261031,selection='random whole scans within RF-only strata; no position errors',rows=panel),indent=2)+'\n')
    with (OUT/'phase-cohort-audit.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='checks'],lineterminator='\n');w.writeheader();w.writerows({k:v for k,v in r.items() if k!='checks'} for r in rows)
    print(json.dumps(summary,indent=2));print('Panel:',[(r['case'],r['track_id'],r['panel_role']) for r in panel])

if __name__=='__main__':run()
