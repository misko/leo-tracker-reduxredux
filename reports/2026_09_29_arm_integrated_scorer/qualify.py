"""One-dwell saved-IQ parity and timing qualification; never an RF collector."""
import argparse,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
import numpy as np
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def science(row):return {'receiver_id':row['receiver_id'],'probe_index':row['probe_index'],'candidates':row['candidates']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,default=HERE/'builds/host-v3/cohort_integrated');parser.add_argument('--output',default='qualification.json')
    args=parser.parse_args();candidate=args.candidate.resolve()
    baseline=ROOT/'2026_09_29_arm_compile_pack/builds/limited-complex-v2/host/cohort_fine_precision_limited_complex_v2_host'
    reference=ROOT/'2026_09_29_arm_low_precision/host704-limited-v2/rows.jsonl'
    old=json.loads(reference.read_text().splitlines()[0]);ctx=old['context']
    features={}
    feature_path=ROOT/'2026_09_29_arm_lag_discovery/ds7-704-v1/rows.jsonl'
    for row in map(json.loads,feature_path.read_text().splitlines()):
        c=row['context'];features[(c['session_id'],c['visit_index'],row['window'],row['rx'])]=row
    oracle=json.loads((a.ORACLE/'oracle.json').read_text())
    templates={(c['context']['rate_hz'],c['context']['target']['edge']):c['templates'] for c in oracle['cases']}
    template=templates[(ctx['rate_hz'],ctx['target']['edge'])]
    paths=[a.ORACLE/template[k]['file'] for k in ('exact','control')]
    n=round(ctx['rate_hz']/750);regions=[]
    for window in range(11):
        for rx in range(2):
            centers=features[(ctx['session_id'],ctx['visit_index'],window,rx)]['ranked_epochs']['combined'][:4]
            epochs=sorted({v for c in centers for v in range(max(0,c-4),min(n,c+5))})
            regions.append(str(len(epochs))+' '+' '.join(map(str,epochs)))
    with tempfile.TemporaryDirectory(prefix='integrated-ci16-') as tmp:
        tmp=Path(tmp);raw=tmp/'input.ci16';np.load(a.INPUTS/ctx['file'],allow_pickle=False).tofile(raw)
        region=tmp/'regions.txt';region.write_text('\n'.join(regions)+'\n')
        outputs={};timings={}
        for label,binary in [('baseline',baseline),('candidate',candidate)]:
            started=time.perf_counter();run=subprocess.run([str(binary),str(ctx['rate_hz']),*map(str,paths),str(raw),str(region)],capture_output=True,text=True,check=True)
            timings[label]=time.perf_counter()-started;assert not run.stderr
            outputs[label]=list(map(json.loads,run.stdout.splitlines()))
    assert len(outputs['baseline'])==len(outputs['candidate'])==22
    changed=[i for i,(x,y) in enumerate(zip(outputs['baseline'],outputs['candidate'])) if science(x)!=science(y)]
    pairs=[(a,b) for x,y in zip(outputs['baseline'],outputs['candidate']) for a,b in zip(x['candidates'],y['candidates'])]
    score_fields=('exact_score','control_score','margin')
    maximum={field:max((abs(a[field]-b[field]) for a,b in pairs),default=0) for field in score_fields}
    maximum['tracking_cfo_hz']=max((abs(a['tracking_cfo_hz']-b['tracking_cfo_hz']) for a,b in pairs),default=0)
    sign_changes=sum((a['margin']>0)!=(b['margin']>0) for a,b in pairs)
    structural_changes=sum(any(a[k]!=b[k] for k in ('coarse_epoch','coarse_bin','refined_epoch','acquired_cfo_hz')) for a,b in pairs)
    result={'schema':'arm-integrated-scorer-qualification/v1','complete':True,'saved_dwells':1,'windows':22,
      'candidate_entries':sum(x['candidate_count'] for x in outputs['candidate']),'changed_windows':changed,
      'scientific_outputs_identical':not changed,'wall_seconds':timings,'candidate_binary_sha256':sha(candidate),
      'baseline_binary_sha256':sha(baseline),'context':ctx,'scope':'one saved-IQ dwell; no ARM execution and no RF collection'}
    result['precision_comparison']={'paired_candidates':len(pairs),'structural_changes':structural_changes,
      'maximum_absolute_delta':maximum,'margin_sign_changes':sign_changes,
      'near_threshold_reference_margins':sum(abs(a['margin'])<=maximum['margin'] for a,b in pairs)}
    result['reported_budgets']={k:outputs['candidate'][0].get(k) for k in ('fine_frame_budget','conditioned_frame_budget') if k in outputs['candidate'][0]}
    result['environment_budgets']={k:os.environ.get(k) for k in ('LEO_FINE_FRAME_BUDGET','LEO_CONDITIONED_FRAME_BUDGET')}
    (HERE/args.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
