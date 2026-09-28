"""Evaluate approximate native GLRT tracking against sealed original windows."""
import json
from pathlib import Path
import argparse, hashlib, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

EPOCH_TOL=2; CFO_TOL=8000.; GATE=.025
def positives(candidates): return [x for x in candidates if x['margin']>=GATE]
def match(reference,native):
    owner={}; pairs=[]
    def visit(i,seen):
        x=reference[i]; choices=[j for j,y in enumerate(native) if abs(x['epoch_sample']-y['epoch'])<=EPOCH_TOL and abs(x['tracking_cfo_hz']-y['tracking_cfo_hz'])<=CFO_TOL]
        for j in choices:
            if j in seen: continue
            seen.add(j)
            if j not in owner or visit(owner[j],seen): owner[j]=i;return True
        return False
    for i in range(len(reference)): visit(i,set())
    return [(i,j,abs(reference[i]['epoch_sample']-native[j]['epoch']),abs(reference[i]['tracking_cfo_hz']-native[j]['tracking_cfo_hz'])) for j,i in owner.items()]
def score(native_rows, baseline_rows):
    expected={(x['receiver_id'],x['probe_index']):x for x in baseline_rows}; got={}; errors=[]
    for row in native_rows:
        key=(row['receiver_id'],row['probe_index'])
        if key in got: errors.append({'key':key,'error':'duplicate_native_window'});continue
        got[key]=row
    counts={'baseline_positive':0,'native_positive':0,'matched_positive':0,'baseline_positive_windows':0,'native_positive_windows':0,'recovered_positive_windows':0,'actual_glrt_attempts':0,'total_cpu_ms':0.}
    for key,base in expected.items():
        ref=positives(base['candidates']); counts['baseline_positive']+=len(ref);counts['baseline_positive_windows']+=bool(ref)
        row=got.get(key)
        if row is None: errors.append({'key':key,'error':'missing_native_window'});continue
        nat=positives(row.get('candidates',[])); counts['native_positive']+=len(nat);counts['native_positive_windows']+=bool(nat)
        m=match(ref,nat);counts['matched_positive']+=len(m);counts['recovered_positive_windows']+=bool(m);counts['actual_glrt_attempts']+=row.get('candidate_eval_attempts',0);counts['total_cpu_ms']+=row.get('timings_ms',{}).get('total_cpu',0.)
    for key in got:
        if key not in expected: errors.append({'key':key,'error':'unexpected_native_window'})
    counts['missed_positive']=counts['baseline_positive']-counts['matched_positive'];counts['added_positive']=counts['native_positive']-counts['matched_positive']
    return {'counts':counts,'errors':errors}
def sealed_baseline(path,context):
    for line in Path(path).read_text().splitlines():
        x=json.loads(line);c=x['context']
        if x['method']=='original' and x['repeat']==0 and c['session_id']==context['session_id'] and c['visit_index']==context['visit_index']: return x['result']['probes']
    raise KeyError('sealed baseline dwell missing')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(binary,output,refresh,radius=1,fallback=0,workers=4,all_sealed=False):
    root=Path(__file__).resolve().parents[1]; inputs=Path('/var/tmp/leo-ds7-large-arm-20260928'); oracle=Path('/var/tmp/leo-arm-full-search-oracle-allrates'); base=root/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    spec=json.loads((inputs/'inputs.json').read_text())['rows'];
    if not all_sealed:
        spec=[r for rate in (2500000,5000000,7500000,10000000) for edge in ('lower','upper') for r in [x for x in spec if x['rate_hz']==rate and x['target']['edge']==edge][:8]]
    tm={(c['context']['rate_hz'],c['context']['target']['edge']):c['templates'] for c in json.loads((oracle/'oracle.json').read_text())['cases']};output.mkdir(); rec={'schema':'tracking-sweep/v1','refresh':refresh,'radius':radius,'fallback':fallback,'binary_sha256':sha(binary),'planned_dwells':len(spec),'planned_windows':len(spec)*22,'complete':False};(output/'run.json').write_text(json.dumps(rec,indent=2)+'\n')
    def one(row,temp):
        raw=temp/(row['file']+'.ci16');np.asarray(np.load(inputs/row['file'],allow_pickle=False),dtype='<i2').tofile(raw);t=tm[(row['rate_hz'],row['target']['edge'])];p=subprocess.run([str(binary),str(row['rate_hz']),str(oracle/t['exact']['file']),str(oracle/t['control']['file']),str(raw),str(refresh),str(radius),str(fallback)],text=True,capture_output=True);raw.unlink(missing_ok=True); rows=[json.loads(x) for x in p.stdout.splitlines()];return {'context':row,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'rows':rows,'audit':score(rows,sealed_baseline(base,row))}
    with tempfile.TemporaryDirectory(dir=output) as d,(output/'rows.jsonl').open('x') as f,ThreadPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(one,r,Path(d)) for r in spec]
        for q in as_completed(fs): f.write(json.dumps(q.result())+'\n');f.flush()
    rec['complete']=True;(output/'run.json').write_text(json.dumps(rec,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--refresh',type=int,nargs='+',default=[1,2,3,5,11]);p.add_argument('--radius',type=int,default=1);p.add_argument('--fallback',type=int,default=0);p.add_argument('--all-sealed',action='store_true');a=p.parse_args()
 for x in a.refresh: run(a.binary,a.output/f'refresh{x}',x,a.radius,a.fallback,a.workers,a.all_sealed)
