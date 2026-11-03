"""Quantify what the frozen whole-visit holdout actually separates."""
import bisect
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]/'2026_09_30_ds11_single10'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def summarize_track(t):
    train=sorted(float(x) for x,m in zip(t['times_s'],t['training_mask'],strict=True) if m)
    held=[float(x) for x,m in zip(t['times_s'],t['training_mask'],strict=True) if not m]
    gaps=[];inside=0
    for x in held:
        if not train:continue
        j=bisect.bisect_left(train,x);neighbors=train[max(0,j-1):min(len(train),j+1)]
        gaps.append(min(abs(x-y) for y in neighbors));inside+=train[0]<=x<=train[-1]
    return dict(training_rows=len(train),held_rows=len(held),held_with_same_track_training=len(gaps),
                held_inside_training_span=inside,nearest_training_gap_s=gaps)
def quantile(values,q):
    s=sorted(values);p=(len(s)-1)*q;i=int(p)
    return s[i]+(s[min(i+1,len(s)-1)]-s[i])*(p-i)
def main():
    plan=read(BASE/'plan.json');sources={str(BASE/'plan.json'):digest(BASE/'plan.json')};rows=[];all_gaps=[]
    for index,entry in enumerate(plan['inputs']):
        artifact=next(a for a in entry['artifacts'] if a['kind']=='observations');path=Path(artifact['path'])
        assert digest(path)==artifact['sha256'].removeprefix('sha256:');sources[str(path)]=digest(path)
        doc=read(path);assert doc['session_id']==entry['session_id'] and doc['manifest_sha256']==entry['manifest_sha256']
        visit_masks={};counts=dict(training_rows=0,held_rows=0,held_with_same_track_training=0,held_inside_training_span=0);gaps=[]
        for t in doc['tracks']:
            for visit,mask in zip(t['visits'],t['training_mask'],strict=True):
                if visit in visit_masks:assert visit_masks[visit]==mask
                visit_masks[visit]=mask
            r=summarize_track(t)
            for k in counts:counts[k]+=r[k]
            gaps.extend(r['nearest_training_gap_s'])
        all_gaps.extend(gaps)
        rows.append(dict(index=index,session_id=doc['session_id'],tracks=len(doc['tracks']),**counts,
                         distinct_training_visits=sum(visit_masks.values()),distinct_held_visits=sum(not m for m in visit_masks.values()),
                         nearest_training_gap_s_quantiles=[quantile(gaps,q) for q in (.5,.9,.99,1)]))
    total={k:sum(r[k] for r in rows) for k in ('tracks','training_rows','held_rows','held_with_same_track_training','held_inside_training_span')}
    total['same_track_training_fraction']=total['held_with_same_track_training']/total['held_rows']
    total['within_training_span_fraction']=total['held_inside_training_span']/total['held_rows']
    total['nearest_training_gap_s_quantiles']=[quantile(all_gaps,q) for q in (.5,.9,.99,1)]
    for path in (Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',HERE.parents[2]/'tools/ds7_export_baseline.py'):
        sources[str(path)]=digest(path)
    result=dict(rows=rows,summary=total,quantile_levels=[.5,.9,.99,1],whole_visit_partition_consistent=True,
                population='all exported tracks, before bank eligibility filtering',sources=sources,position_fits=0)
    with (HERE/'outcome.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(total,indent=2))
if __name__=='__main__':main()
