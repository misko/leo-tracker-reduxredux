import csv,json
from pathlib import Path
base=Path('reports/2026_09_30_native_adaptive_deployment/tracking')
cand={r['candidate_id']:r for r in csv.DictReader(open(base/'candidates.tsv'),delimiter='\t')}
# parse native
tracks=[]
for line in open(base/'native-tracks.tsv'):
 f=line.rstrip('\n').split('\t')
 if f[0]=='TRACK':
  tracks.append(dict(index=int(f[1]),segment=f[2],tracklet=f[3],lane=(int(f[5]),f[6],int(f[4]),float(f[7])),slope=float(f[11]),intercept=float(f[12]),rms=float(f[13]),points=[]))
 elif f[0]=='POINT': tracks[int(f[1])]['points'].append(dict(id=f[2],source=f[3],alias=int(f[4]),raw=float(f[5]),dealias=float(f[6])))
oracle=json.load(open(base/'oracle-tracks.json'))['tracks']
by={ (tuple(t['lane_key']),frozenset(cand[p['candidate_id']]['source_group_id'] for p in t['points'])):t for t in oracle}
rows=[]
for n in tracks:
 key=(n['lane'],frozenset(p['source'] for p in n['points']))
 o=by[key]
 op={cand[p['candidate_id']]['source_group_id']:p for p in o['points']}
 for p in n['points']:
  q=op[p['source']]
  if p['id']!=q['candidate_id']:
   a=cand[p['id']];b=cand[q['candidate_id']]
   siblings=[r for r in cand.values() if r['source_group_id']==p['source']]
   rows.append(dict(native_track=n['index'],native_tracklet=n['tracklet'],oracle_tracklet=o['tracklet_id'],source=p['source'],native=p['id'],oracle=q['candidate_id'],native_cfo=float(a['measured_cfo_hz']),oracle_cfo=float(b['measured_cfo_hz']),delta=float(a['measured_cfo_hz'])-float(b['measured_cfo_hz']),weight_native=min(max(float(a['margin']),0)/max(float(a['control_score']),.02),16),weight_oracle=min(max(float(b['margin']),0)/max(float(b['control_score']),.02),16),siblings=[(r['candidate_id'],float(r['measured_cfo_hz']),float(r['margin']),float(r['control_score'])) for r in siblings]))
print(json.dumps(rows,indent=2))
