import csv,hashlib,json,math,os,sys,time
from collections import defaultdict
from pathlib import Path

EXPECTED_CFO_LINES_SHA256='e7fe080db15ce17e183d12582bad8e638f5fca973f9cefb26e88c0bfc938c7ea'
oracle_source=os.environ.get('LEO_C4_ORACLE_SOURCE')
if not oracle_source:
 raise SystemExit('set LEO_C4_ORACLE_SOURCE to the reviewed server src directory')
oracle_source=Path(oracle_source).resolve()
cfo_source=oracle_source/'leo/analysis/cfo_lines.py'
if not cfo_source.is_file() or hashlib.sha256(cfo_source.read_bytes()).hexdigest()!=EXPECTED_CFO_LINES_SHA256:
 raise SystemExit('oracle cfo_lines.py is absent or has the wrong SHA-256')
sys.path.insert(0,str(oracle_source))
import numpy as np
import leo.analysis.cfo_lines as cfo
if Path(cfo.__file__).resolve()!=cfo_source:
 raise SystemExit('Python imported a different cfo_lines.py')
BASE='reports/2026_09_30_native_adaptive_deployment/tracking'
rows=list(csv.DictReader(open(BASE+'/candidates.tsv'),delimiter='\t'))
bylane=defaultdict(list)
for r in rows:
 key=(int(r['channel']),r['edge'],int(r['receiver_id']),float(r['actual_rf_hz']))
 bylane[key].append(r)
oracle=json.load(open(BASE+'/oracle-tracks.json'))['tracks']
oracle_by_lane=defaultdict(list)
byid={r['candidate_id']:r for r in rows}
for t in oracle: oracle_by_lane[tuple(t['lane_key'])].append(t)
common_kwargs=dict(minimum_slope_hz_per_s=-15000,maximum_slope_hz_per_s=15000,residual_gate_hz=2500,maximum_gap_s=4,minimum_span_s=3,minimum_support=6,minimum_point_weight=.1,maximum_tracks=8)
orig=cfo._fit_alias_line

def make_fit(solver):
 def fit(indexes,points,*,initial_slope,initial_intercept,alias_spacing_hz,algorithm,arrays):
  times,frequency,weights=arrays
  st=times[indexes]; sf=frequency[indexes]; sw=np.maximum(weights[indexes],np.finfo(float).eps)
  # preserve np.average t0 like oracle; separate tests can vary it
  t0=float(np.average(st,weights=sw)); slope=float(initial_slope); center=float(initial_intercept+initial_slope*t0)
  for _ in range(4):
   pred=center+slope*(st-t0)
   lifted=sf-np.round((sf-pred)/alias_spacing_hz)*alias_spacing_hz
   slope,center=solver(st-t0,lifted,sw)
  intercept=float((center-slope*t0)%alias_spacing_hz)
  residual=cfo.circular_residual_hz(sf,slope*st+intercept,alias_spacing_hz)
  ids=tuple(points[int(i)].point_id for i in indexes)
  ident=hashlib.sha256((algorithm+'\0'+'\0'.join(ids)).encode()).hexdigest()
  gaps=np.diff(st)
  return cfo.LineSegment(algorithm=algorithm,segment_id='sha256:'+ident,point_ids=ids,
   start_s=float(np.min(st)),end_s=float(np.max(st)),support=int(indexes.size),weighted_support=float(np.sum(sw)),
   slope_hz_per_s=float(slope),intercept_hz=intercept,intercept_mod_alias_hz=intercept,
   residual_rms_hz=float(np.sqrt(np.average(residual**2,weights=sw))),residual_max_hz=float(np.max(np.abs(residual))),
   maximum_gap_s=float(np.max(gaps)) if gaps.size else 0.)
 return fit

def normal(x,y,w):
 sxx=sx=sw=sxy=sy=0.0
 for X,Y,W in zip(x,y,w):
  X=float(X);Y=float(Y);W=float(W)
  sxx+=W*X*X;sx+=W*X;sw+=W;sxy+=W*X*Y;sy+=W*Y
 d=sxx*sw-sx*sx
 return ((sxy*sw-sx*sy)/d,(sxx*sy-sx*sxy)/d) if abs(d)>np.finfo(float).eps else (0.,sy/sw)
def fsum_normal(x,y,w):
 vals=[(float(X),float(Y),float(W)) for X,Y,W in zip(x,y,w)]
 sxx=math.fsum(W*X*X for X,Y,W in vals);sx=math.fsum(W*X for X,Y,W in vals);sw=math.fsum(W for X,Y,W in vals)
 sxy=math.fsum(W*X*Y for X,Y,W in vals);sy=math.fsum(W*Y for X,Y,W in vals);d=sxx*sw-sx*sx
 return ((sxy*sw-sx*sy)/d,(sxx*sy-sx*sxy)/d)
def centered(x,y,w):
 vals=[(float(X),float(Y),float(W)) for X,Y,W in zip(x,y,w)]
 sw=math.fsum(W for X,Y,W in vals); sx=math.fsum(W*X for X,Y,W in vals); sy=math.fsum(W*Y for X,Y,W in vals)
 mx=sx/sw; my=sy/sw
 sxx=math.fsum(W*(X-mx)*(X-mx) for X,Y,W in vals);sxy=math.fsum(W*(X-mx)*(Y-my) for X,Y,W in vals)
 a=sxy/sxx;return a,my-a*mx
def mgs(x,y,w):
 a0=[];a1=[];b=[]
 for X,Y,W in zip(x,y,w):
  q=math.sqrt(float(W));a0.append(float(X)*q);a1.append(q);b.append(float(Y)*q)
 r00=math.sqrt(math.fsum(v*v for v in a0));q0=[v/r00 for v in a0]
 r01=math.fsum(q*v for q,v in zip(q0,a1));u1=[v-r01*q for v,q in zip(a1,q0)]
 r11=math.sqrt(math.fsum(v*v for v in u1));q1=[v/r11 for v in u1]
 z0=math.fsum(q*v for q,v in zip(q0,b));z1=math.fsum(q*v for q,v in zip(q1,b))
 beta=z1/r11;alpha=(z0-r01*beta)/r00
 return alpha,beta

def run(name,solver):
 cfo._fit_alias_line=orig if solver is None else make_fit(solver)
 got=[];start=time.time()
 for lane,rs in sorted(bylane.items()):
  first=min(int(r['support_center_utc_ns']) for r in rs);scale=11200000000/lane[3]
  pts=tuple(cfo.CfoPoint(r['candidate_id'],(int(r['support_center_utc_ns'])-first)/1e9,float(r['measured_cfo_hz'])*scale,float(r['exact_score']),float(r['control_score']),float(r['margin']),r['source_group_id']) for r in rs)
  common=cfo.LineDetectionConfig(alias_spacing_hz=(1/4.4e-6)*scale,**common_kwargs)
  segs=cfo.weighted_hough_lines(pts,cfo.HoughConfig(common=common,slope_bins=3601,intercept_bins=512,peak_candidates=64))
  for s in segs: got.append((lane,s))
 expected={ (tuple(t['lane_key']),frozenset(byid[p['candidate_id']]['source_group_id'] for p in t['points'])):t for t in oracle}
 mism=[]; missing=0
 for lane,s in got:
  sources=frozenset(byid[i]['source_group_id'] for i in s.point_ids);o=expected.get((lane,sources))
  if o is None: missing+=1;continue
  op={byid[p['candidate_id']]['source_group_id']:p['candidate_id'] for p in o['points']}
  for i in s.point_ids:
   src=byid[i]['source_group_id']
   if i!=op[src]: mism.append((src,i,op[src]))
 print(json.dumps(dict(solver=name,seconds=time.time()-start,tracks=len(got),membership_missing=missing,candidate_mismatches=len(mism),mismatch_sources=[x[0] for x in mism]),sort_keys=True))
for name,solver in [('lapack',None),('normal',normal),('fsum_normal',fsum_normal),('centered_fsum',centered),('mgs_fsum',mgs)]:run(name,solver)
