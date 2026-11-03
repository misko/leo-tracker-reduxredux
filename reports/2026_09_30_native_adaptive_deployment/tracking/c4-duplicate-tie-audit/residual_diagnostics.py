import csv,json,math
from pathlib import Path
base=Path('reports/2026_09_30_native_adaptive_deployment/tracking')
cand={r['candidate_id']:r for r in csv.DictReader(open(base/'candidates.tsv'),delimiter='\t')}
# parse native
native=[]
for line in open(base/'native-tracks.tsv'):
 f=line.rstrip().split('\t')
 if f[0]=='TRACK': native.append(dict(index=int(f[1]),lane=(int(f[5]),f[6],int(f[4]),float(f[7])),reference=int(f[10]),slope=float(f[11]),intercept=float(f[12]),points=[]))
 elif f[0]=='POINT': native[int(f[1])]['points'].append(dict(id=f[2],source=f[3]))
oracle=json.load(open(base/'oracle-tracks.json'))['tracks']
by={ (tuple(t['lane_key']),frozenset(cand[p['candidate_id']]['source_group_id'] for p in t['points'])):t for t in oracle}
def residual(freq,pred,space): return (freq-pred+space/2)%space-space/2
for n in native:
 o=by[(n['lane'],frozenset(p['source'] for p in n['points']))]
 op={cand[p['candidate_id']]['source_group_id']:p for p in o['points']}
 for p in n['points']:
  q=op[p['source']]
  if p['id']==q['candidate_id']:continue
  rf=n['lane'][3]; scale=11200000000.0/rf; space=(1/4.4e-6)*scale
  t=(int(cand[p['id']]['support_center_utc_ns'])-n['reference'])/1e9
  vals=[]
  for label,fit in [('N',n),('O',{'slope':o['normalized_rate_hz_per_s'],'intercept':o['normalized_intercept_hz']})]:
   pred=fit['slope']*t+fit['intercept']
   a=float(cand[p['id']]['measured_cfo_hz'])*scale
   b=float(cand[q['candidate_id']]['measured_cfo_hz'])*scale
   vals.append((label,residual(a,pred,space),residual(b,pred,space),abs(residual(a,pred,space))-abs(residual(b,pred,space))))
  print(n['index'],p['source'][-8:],p['id'][-8:],q['candidate_id'][-8:],'t',t,'dcfo',float(cand[p['id']]['measured_cfo_hz'])-float(cand[q['candidate_id']]['measured_cfo_hz']),'fits',vals,'fitdelta',n['slope']-o['normalized_rate_hz_per_s'],n['intercept']-o['normalized_intercept_hz'])
