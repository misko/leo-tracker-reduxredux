"""Physical-residual coarse fallback independent of narrow timing-vote modes.

Development-only fixed calibration. One-second timing anchors complement the
root-mode search; exact 600 Hz visibility/coherence gates remain unchanged.
This does not certify discovery completeness or validated assigned coverage.
"""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,ALIAS_HZ,digest
from adaptive_discovery import coherent_segments
from feasible_tracklets import select
from audit_proposals import maximum_group_pairs


def supported_extension_offsets(times,nodes,common,half_range=59.):
    offsets=np.arange(-half_range,half_range+.001,1.)
    valid=(np.min(times)+common+offsets>=np.min(nodes))&(np.max(times)+common+offsets<np.max(nodes))
    return offsets[valid&(np.abs(offsets)>20.)]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--extend-timing',action='store_true')
    args=parser.parse_args();sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,SharedPredictionPlan,circular_residual
    case=Case(args.scan);d=case.data
    source=ROOT/'development-expanded'/f'{args.scan}-proposals.json'
    original=json.loads(source.read_text())['proposals']
    discovery_path=ROOT/'development-discovery'/f'{args.scan}-proposals.json';discovery=json.loads(discovery_path.read_text())
    fit_path=OLD/'exhaustive-subset'/f'{args.scan}-receipt.json'
    if discovery['source_sha256']!=digest(fit_path):raise ValueError('Calibration lineage changed')
    fit=json.loads(fit_path.read_text())['arms']['fitted-c']['fit'];params=np.array(fit['parameters'])
    correction=case.features@np.array(fit['rf_coefficient_hz_per_ghz']);common=discovery['common_timing_s']
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:reps=a['canonical_rows']
    base_source=ROOT/'coarse-fallback'/f'{args.scan}.json'
    if args.extend_timing:original+=json.loads(base_source.read_text())['new_proposals']
    target=ROOT/('extended-coarse-fallback' if args.extend_timing else 'coarse-fallback')/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    offsets=supported_extension_offsets(d.times,d.nodes,common) if args.extend_timing else np.arange(-20.,20.001,1.)
    start=time.monotonic();deadline=start+180;proposals=[]
    for begin in range(0,len(d.numbers),16):
        ids=np.arange(begin,min(begin+16,len(d.numbers)));plan=SharedPredictionPlan(d,ids)
        for offset in offsets:
            if time.monotonic()>deadline:raise TimeoutError('Fallback discovery exceeded 180 seconds')
            trial=params.copy();trial[6+ids]=common+offset
            prediction,visibility,_=plan.predict(trial)
            prediction=prediction.reshape(len(d.times),-1)+correction[:,None]
            residual=circular_residual(d.measured[:,None],prediction,ALIAS_HZ);visibility=visibility.reshape(residual.shape)
            for col,index in enumerate(ids):
                good=reps[visibility[reps,col]&(np.abs(residual[reps,col])<=600)]
                if len(np.unique(d.group[good]))<10:continue
                segments=coherent_segments(good,d.times,d.group,d.receiver,d.channel,residual[:,col])
                if not segments:continue
                for s in segments:
                    rows=good[(d.receiver[good]==s['receiver'])&(d.channel[good]==s['channel'])
                        &(d.times[good]>=s['start_s']-1e-7)&(d.times[good]<=s['end_s']+1e-7)]
                    s['eligible_rows']=rows.tolist();s['eligible_residual_native_hz']=residual[rows,col].tolist()
                proposals.append(dict(catalog_number=int(d.numbers[index]),satellite_index=int(index),
                    total_timing_s=common+float(offset),offset_s=float(offset),segments=segments))
        if begin%160==0:print(args.scan,'coarse fallback',int(ids[-1])+1,'/',len(d.numbers),len(proposals),'modes',flush=True)
    elapsed=time.monotonic()-start;combined=original+proposals;edges={}
    for p in combined:
        for s in p['segments']:
            for row in s['eligible_rows']:edges.setdefault(row,set()).add(p['catalog_number'])
    matches=[]
    for group in np.unique(d.group):
        rows=np.flatnonzero(d.group==group)
        matches.extend(maximum_group_pairs({int(r):edges[int(r)] for r in rows if int(r) in edges}))
    chosen=select(combined,d.group,d.times,.8/(13 if args.scan=='A' else 15))
    prior_catalogs={p['catalog_number'] for p in original};new_catalogs=sorted({p['catalog_number'] for p in proposals}-prior_catalogs)
    summary=dict(scan=args.scan,new_modes=len(proposals),new_catalogs=new_catalogs,combined_modes=len(combined),
        optimistic_exclusive_bound=len(matches),optimistic_exclusive_fraction=len(matches)/len(reps),
        selected_assignments=len(chosen['assignments']),raw_selected_coverage=len(chosen['assignments'])/len(reps),
        discovery_seconds=elapsed,total_seconds=time.monotonic()-start,offsets_s=offsets.tolist(),
        ephemeris_node_range_s=[float(d.nodes[0]),float(d.nodes[-1])],
        selected_extended_modes=sum(abs(combined[int(pi)]['offset_s'])>20 for pi in chosen['selected_modes'].values()))
    target.parent.mkdir(exist_ok=True)
    with target.open('x') as stream:json.dump(dict(scope=__doc__,summary=summary,new_proposals=proposals,
        selection=chosen,source_sha256={str(p):digest(p) for p in ([source,discovery_path,fit_path,base_source] if args.extend_timing else [source,discovery_path,fit_path])}),stream,indent=2)
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
