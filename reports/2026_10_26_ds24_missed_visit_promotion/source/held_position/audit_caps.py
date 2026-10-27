"""Describe cap checkpoints without promoting their partial endpoint values."""
import argparse
from pathlib import Path
from position import HERE,read,write,sha

def checkpoint_state(root,case):
    root=Path(root);folder=root/case
    files={'discovery_progress':folder/'progress_radio_noise.json','discovery_final':folder/'fit_radio_noise.json','initial_association':folder/'result.json','algo02_refinement':folder/'algo02_result.json','family_nominations':root/'family_cavity'/(case+'.json'),'family_position':root/'family_cavity/position'/(case+'.json')}
    present={k:str(p) for k,p in files.items() if p.exists()}
    progress=read(files['discovery_progress']) if files['discovery_progress'].exists() else {}
    text=(root/'fresh_algo02.log').read_text() if (root/'fresh_algo02.log').exists() else ''
    completed_seeds=sum(line.startswith(case+' fresh ') for line in text.splitlines())
    branches=len(progress.get('choices',[]))
    if 'family_position' in present:last='family_position_output_present';active='finalization_or_complete'
    elif 'family_nominations' in present:last='family_nominations';active='family_position'
    elif 'algo02_refinement' in present:last='algo02_refinement';active='signed_phase_prior_or_family_nomination'
    elif 'initial_association' in present:last='initial_association';active='algo02_refinement'
    elif 'discovery_final' in present:last='discovery';active='initial_association'
    elif branches:last='paired_discovery_branches';active='discovery'
    elif completed_seeds:last='RF_seed_nomination';active='discovery'
    else:last='no_completed_scientific_checkpoint';active='discovery_or_import'
    return dict(last_completed_stage=last,active_stage_at_cap=active,completed_RF_seed_messages=completed_seeds,completed_paired_discovery_branches=branches,checkpoint_count=len(present),checkpoint_files=present,checkpoint_hashes={str(p):sha(p) for p in files.values() if p.exists()},partial_endpoints_qualified=False,partial_geographic_values_used=False)

def main(output):
    protocols=[HERE/'baseline_v3/protocol.json',HERE/'baseline_queue/protocol.json',HERE/'coherent_candidates/protocol.json']
    jobs={}
    for p in protocols:
        if p.exists():
            for j in read(p)['jobs']:jobs[j['root']]=j
    rows=[]
    for j in jobs.values():
        root=Path(j['root']);execution=root/'execution.json'
        if execution.exists() and read(execution)['status']=='capped':
            rows.append(dict(j,status='capped',seconds=read(execution)['seconds'],**checkpoint_state(root,j['case'])))
    write(output,dict(source_sha256=sha(__file__),cap_count=len(rows),rows=rows,no_partial_endpoint_used=True))
    print([(r['case'],r['variant'],r['last_completed_stage'],r['checkpoint_count']) for r in rows],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output)
