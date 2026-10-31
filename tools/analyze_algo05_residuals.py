"""Rank post gap-conditional residuals from sealed DS26/DS27 paired evidence.

This is reporting over existing fits, not a new inference or production backfill.
The prior ranking implementation is supplied explicitly as --ranking-tool.
"""
import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from algo05_recovery_worker import select
from leo.contracts.fast_graph_position_v4 import qualify

def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def checked(path,expected):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected.removeprefix('sha256:'):
        raise ValueError('Changed frozen evidence: '+str(path))
    return read(path) if Path(path).suffix=='.json' else None

def run(args):
    spec=importlib.util.spec_from_file_location('rank_native_residuals',args.ranking_tool)
    rank=importlib.util.module_from_spec(spec);spec.loader.exec_module(rank)
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    d26=Path('/srv/bulk/leo/research/ds26-confident-recovery-20261031')
    d27=Path('/srv/bulk/leo/research/ds27-confident-recovery-20261031')
    for root in (d26,d27):
        seal=read(root/'inference-seal.json')
        for p,h in seal['files'].items():checked(p,h)
    protocol=read(d26/'protocol.json');execution=read(d26/'execution.json')
    index27=read('/srv/bulk/leo/research/ds27-algo04-20261031/analysis-index.json')
    rf27={r['case']:r for r in read(d27/'rf-decisions.json')['decisions']}
    cases=[];unavailable=[]
    for entry in protocol['roster']:
        if entry['state']!='complete':unavailable.append(entry);continue
        b=checked(entry['baseline_path'],entry['baseline_sha256'])
        root=Path(b['source']).parent
        inventories=list((root/'all-large-track-recovery').glob('*/inventory.json'))
        if len(inventories)!=1:raise ValueError('Ambiguous inventory')
        inv=read(inventories[0]);native=Path(inv['job']['root'])/inv['job']['case']
        trials=[t for r in execution if r['case']==entry['case'] for t in r['trials'] if t['mode']=='gap_conditional']
        cases.append(dict(case=entry['case'],root=root,inventory=inventories[0],native=native,
            owners=b['owners'],trials=trials,identities=inv['job']['identities'],baseline_arms=b['arms']))
    for entry in index27['cases']:
        if entry['state']!='complete':unavailable.append(entry);continue
        t=checked(entry['terminal_path'],entry['terminal_sha256']);inv=checked(entry['inventory_path'],entry['inventory_sha256'])
        proof=t['candidate'] if t['decision']=='ALGO04_additive' else t['incumbent']
        arms=proof['selected']['arms'] if proof.get('selected') else proof['baseline']['arms']
        cases.append(dict(case=entry['case'],root=Path(entry['algo04_recovery_path']),inventory=Path(entry['inventory_path']),
            native=Path(entry['observations_path']).parent,owners={a:rank.published_owners(t,a) for a in ('c0','fitted_c')},
            trials=rf27.get(entry['case'],{}).get('trials',[]),identities=entry['identities'],baseline_arms=arms))
    rows=[];summaries=[];contexts={};selections=[];sources={}
    for c in cases:
        obs=read(c['native']/'observations.json');tracks=read(c['native']/'tracks.json');universe={o['observation_id'] for o in obs}
        candidates=[]
        for t in c['trials']:
            if t['mode']!='gap_conditional':continue
            folder=Path(t['path']);folder=folder.parent if folder.suffix=='.json' else folder
            if not (folder/'target_0.json').exists() or not (folder/'exact_owner_replay.json').exists():continue
            fit=read(folder/'target_0.json');audit=read(folder/'exact_owner_replay.json')
            identity=t.get('identity') or read(folder.parent/'annotation/result.json')['annotation']
            q=qualify(fit,audit,c['owners'],universe)
            candidates.append(dict(track_id=t.get('track_id',str(folder.parent)),path=str(folder),identity=identity,qualification=q))
        selected=select(candidates)
        if selected:
            trial=read(Path(selected['path'])/'target_0.json');owners=trial['arms']['fitted_c']['proposed_owners']
        else:owners=c['owners']['fitted_c']
        local,summary=rank.fragment_rows(c['case'],tracks,obs,owners,c['identities'])
        summary.update(baseline_associated=len(c['owners']['fitted_c']),added_points=len(owners)-len(c['owners']['fitted_c']))
        for r in local:r.update(inventory_path=str(c['inventory']),recovery_path=str(c['root']))
        rows+=local;summaries.append(summary)
        contexts[c['case']]=dict(tracks=tracks,observations=obs,associated=set(owners))
        selections.append(dict(case=c['case'],selected=selected))
        for path in (c['native']/'tracks.json',c['native']/'observations.json',c['inventory']):sources[str(path)]=rank.digest(path)
    rows.sort(key=lambda r:(-r['duration_s'],-r['points'],r['case'],r['track_index'],r['fragment_number']))
    for i,r in enumerate(rows,1):r['rank']=i
    write(out/'selections.json',selections);write(out/'per-scan.json',summaries)
    write(out/'sources.json',dict(files=sources,ranking_tool=str(args.ranking_tool),ranking_sha256=rank.digest(args.ranking_tool),
        mode='gap_conditional',inference_replayed=False,prior_sealed_fits=True,unavailable=unavailable))
    with gzip.open(out/'all-residual-fragments.json.gz','wt') as f:json.dump(rows,f)
    rank.write_csv(out/'per-scan.csv',summaries)
    for dataset in ('DS26','DS27'):
        top=[r for r in rows if r['case'].startswith(dataset)][:10]
        write(out/(dataset+'-top10.json'),top);rank.write_csv(out/(dataset+'-top10.csv'),top)
        directory=out/dataset;directory.mkdir()
        rank.export_plot_packet(directory/'plot-inputs.json.gz',top,contexts)
        rank.render(directory,top,contexts)
        print(dataset,[(r['case'],r['key'],r['points'],round(r['duration_s'],1)) for r in top])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ranking-tool',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
