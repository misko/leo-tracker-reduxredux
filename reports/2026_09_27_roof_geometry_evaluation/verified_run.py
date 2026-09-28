"""Verified public-port evaluation; reads only complete published analysis bundles."""
from __future__ import annotations
import hashlib,json,math
from collections import Counter
from pathlib import Path
import numpy as np
from leo.storage import BundleNotFoundError
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE=Path(__file__).resolve().parent; ROOT=Path('/srv/bulk/leo'); POSE=ROOT/'capture-pose/gauss-r20-roof-20260926-v1'
SESSIONS=['scan-fw-2e6b78f0cd0cbbbc','scan-fw-3221795d82a1c7ec','scan-fw-195bdbb87ad09b7f','scan-fw-60d9d1e77c14da0a','scan-fw-cd6a029d633dcc0e','scan-fw-c78fb2dba2465361','scan-fw-c7e37f65ae9e08b0','scan-fw-5eaaa2a8f8c995b3']
CAL=set(SESSIONS[:5]); HOLD=set(SESSIONS[5:]); ALIAS=1/4.4e-6
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def dig(x):return 'sha256:'+hashlib.sha256(x).hexdigest()
def circ(x,p):return x-round(x/p)*p
def complete_sets(inventory):
 return ({x['session_id'] for x in inventory if x['split']=='calibration' and x['analysis_ready']},{x['session_id'] for x in inventory if x['split']=='holdout' and x['analysis_ready']})
def separated_shift(n,minimum=100):
 if n<2*minimum:return None
 shift=n//2
 assert min(shift,n-shift)>=minimum
 return np.roll(np.arange(n),shift)
def dedup(cs):
 out=[]
 for c in cs:
  if not c.passed_fractional_margin_gate:continue
  key=(round(c.integer_epoch_sample+c.fractional_epoch_offset_samples,3),round(c.fractional_tracking_cfo_hz,1))
  if all(x[0]!=key for x in out):out.append((key,c))
 return [x[1] for x in out]
def load():
 store=ScannerTrackingInputStore(ROOT); captures=AdaptiveHopIqStore(ROOT,read_only=True); inventory=[];rows=[]
 try:
  for i,sid in enumerate(SESSIONS):
   cap=captures.inspect(sid); receipt=cap.manifest.receipt; pose=json.loads((POSE/f'{sid}.json').read_text()); body={k:v for k,v in pose.items() if k!='binding_digest'}
   authority_ok=dig(canon(pose['pose_authority']))==pose['pose_authority_digest']; binding_ok=dig(canon(body))==pose['binding_digest']; source_ok=cap.manifest_sha256==pose['manifest_sha256']
   if not(authority_ok and binding_ok and source_ok):raise RuntimeError(f'pose/source verification failed: {sid}')
   try: inp=store.load(sid); ready=True; reason=None
   except BundleNotFoundError as e:inp=None;ready=False;reason=str(e)
   inventory.append({'session_id':sid,'split':'calibration' if sid in CAL else 'holdout','complete_capture_visits':receipt.terminal.visits_started,'analysis_ready':ready,'readiness_reason':reason,'manifest_sha256':cap.manifest_sha256,'pose_authority_digest_valid':authority_ok,'binding_digest_valid':binding_ok,'source_manifest_verified':source_ok,'analysis_manifest_sha256':None if inp is None else inp.analysis_manifest_sha256})
   if inp is None:continue
   probes={}
   for p in inp.probes:
    k=(p.visit_index,p.probe_index,p.probe_start_ms,p.channel,p.edge)
    if (k,p.receiver_id) in probes:raise RuntimeError(f'duplicate probe {sid} {k}')
    probes[(k,p.receiver_id)]=p
   keys={k for k,rx in probes}; expected=receipt.terminal.visits_started
   if len(keys)!=expected or any((k,rx) not in probes for k in keys for rx in (0,1)):raise RuntimeError(f'incomplete public bundle {sid}')
   for k in sorted(keys):
    rr={rx:probes[(k,rx)] for rx in (0,1)}; rows.append({'session':sid,'visit':k[0],'channel':k[3],'edge':k[4],'rx':{rx:{'detected':bool(dedup(rr[rx].candidates)),'candidates':dedup(rr[rx].candidates),'rate':inp.sample_rate_hz} for rx in (0,1)}})
 finally:store.close();captures.close()
 return inventory,rows
def edges(r,bias=None):
 z=[]
 for a in r['rx'][0]['candidates']:
  for b in r['rx'][1]['candidates']:
   dt=circ((b.integer_epoch_sample+b.fractional_epoch_offset_samples)/r['rx'][1]['rate']-(a.integer_epoch_sample+a.fractional_epoch_offset_samples)/r['rx'][0]['rate'],1/750);df=circ(b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz,ALIAS)
   if abs(dt)<=2.2e-6 and (bias is None or abs(circ(df-bias,ALIAS))<=10000):z.append((dt,df))
 return z
def classify(rows,bias):
 for r in rows:
  d=[r['rx'][x]['detected'] for x in (0,1)]
  r['category']='both_compatible' if all(d) and edges(r,bias) else 'both_unmatched' if all(d) else 'rx0_only' if d[0] else 'rx1_only' if d[1] else 'neither'
 return rows
def baseline(rows,train):
 return {(c,r):(sum(x['rx'][r]['detected'] for x in rows if x['session'] in train and x['channel']==c)+.5)/(sum(x['session'] in train and x['channel']==c for x in rows)+1) for c in range(1,5) for r in (0,1)}
def score(rows,p,test):
 v=[-math.log(p[(x['channel'],r)] if x['rx'][r]['detected'] else 1-p[(x['channel'],r)]) for x in rows if x['session'] in test for r in (0,1)]
 return {'observations':len(v),'mean_log_loss':float(np.mean(v))}
def controls(rows,bias,test):
 fixed=[]
 for sid in test:
  for ch in range(1,5):
   for edge in ('lower','upper'):
    q=[x for x in rows if x['session']==sid and x['channel']==ch and x['edge']==edge];perm=separated_shift(len(q))
    if not q:continue
    if perm is None:continue
    for i,j in enumerate(perm):
     x=dict(q[i]);x['rx']={0:q[i]['rx'][0],1:q[int(j)]['rx'][1]};fixed.append(x)
 swapped=[]
 for r in rows:
  if r['session'] in test:
   x=dict(r);x['rx']={0:r['rx'][1],1:r['rx'][0]};swapped.append(x)
 return Counter(x['category'] for x in classify(fixed,bias)),Counter(x['category'] for x in classify(swapped,-bias))
def main():
 inv,rows=load();cal,hold=complete_sets(inv)
 vals=[e[1] for r in rows if r['session'] in cal for e in edges(r)]; bins=np.arange(-ALIAS/2,ALIAS/2+5000,5000);h,e=np.histogram(vals,bins);k=int(np.argmax(h));bias=float(np.median([x for x in vals if e[k]<=x<e[k+1]]))
 classify(rows,bias); full=baseline(rows,cal); repaired=cal&{SESSIONS[3],SESSIONS[4]};shift,swap=controls(rows,bias,hold)
 out={'status':'verified_public_ports','inventory':inv,'complete_calibration_sessions':sorted(cal),'excluded_incomplete_calibration_sessions':sorted(CAL-cal),'complete_holdout_sessions':sorted(hold),'excluded_incomplete_holdout_sessions':sorted(HOLD-hold),'pairing':{'epoch_tolerance_us':2.2,'cfo_tolerance_hz':10000,'cfo_bias_hz':bias,'provenance':'symbol-motivated epoch tolerance; heuristic CFO tolerance; matching accuracy not calibrated','interpretation':'compatibility only, not identity or power'},'opportunities':{'calibration':dict(Counter(x['category'] for x in rows if x['session'] in cal)),'holdout':dict(Counter(x['category'] for x in rows if x['session'] in hold)),'fixed_long_shift_holdout':dict(shift),'receiver_swap_holdout':dict(swap)},'m0':{'complete_calibration_holdout':score(rows,full,hold),'postrepair_sensitivity_holdout':score(rows,baseline(rows,repaired),hold)},'stages':{'m1':'not yet evaluated','m2':'not yet evaluated','position':'not yet evaluated'},'next_bounded_test':'After remaining bundles publish, use Doppler-only training candidate posteriors to form east-component hypotheses, then cross-fit signed RX margin contrast without using reception to choose identity; compare M0/M1 on all three frozen holdouts and mapping reversal.'}
 (HERE/'verified_results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
