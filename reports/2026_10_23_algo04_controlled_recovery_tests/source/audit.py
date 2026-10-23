"""Fixed-endpoint numerical replay and gate diagnostics; no position optimization."""
from pathlib import Path
import numpy as np
from experiment import OUT,SOURCE,CASES,ARMS,context,apply_trial,paths,gate_slacks
from followup import make_event_problem,attach_event_predictive
from run_algo01_ds23_sample import read,write,sha


def main():
    audits=[];gate_records=[];curves=[]
    protocol=read(OUT/'protocol.json');assert sha(OUT/'source/experiment.py')==protocol['source_sha256']
    assert sha(OUT/'source/followup.py')==read(OUT/'followup_protocol_v2.json')['source_sha256']
    original_protocol=read(SOURCE/'protocol.json')
    root=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
    assert all(sha(root/'tools'/(name+'.py'))==h for name,h in original_protocol['source_hashes'].items())
    for case in CASES:
        d,frozen=context(case)
        assert sha(SOURCE/'raw'/case/'result.json')==protocol['inputs'][case]
        no=read(OUT/'raw'/case/'norescue.json')
        selected=frozen['graph']['selected'];assert selected is not None
        matched=next(t for t in no['trials'] if t['kind']=='default' and t['additions']==selected['additions'])
        dd=apply_trial(d,selected)
        variants={'ordinary_initial':(matched['unconstrained_initial_arms'],[]),
                  'constrained_graph':(selected['arms'],[])}
        if case in CASES[:3]:
            physical=read(OUT/'raw'/case/'physical.json')
            variants.update({name:(v['arms'],v['events']) for name,v in physical['results'].items()})
        for name,(pair,events) in variants.items():
            for arm,saved in pair.items():
                p=make_event_problem(dd['scan'],dd['node'],dd['keep'],arm,np.asarray(saved['phase_reference']),dd['powers'],dd['means'],dd['model'],events)
                attach_event_predictive(p,dd['entries'],dd['powers']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
                delta=c['negative_twice_elbo']-saved['negative_twice_elbo'];assert abs(delta)<1e-5
                slacks=gate_slacks(p,x,dd['entries']);worst=sorted(slacks.items(),key=lambda v:v[1])[:6]
                audits.append(dict(case=case,method=name,arm=arm,objective_difference=delta))
                gate_records.append(dict(case=case,method=name,arm=arm,worst_slacks=worst,
                    all_slacks=slacks,minimum_slack=min(slacks.values()),saved_phase_change_s=saved['final_phase_change_s']))
                if case in CASES[:3]:
                    added={a['component'] for a in selected['additions']}
                    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                        t=p.scan.tracks[i]
                        if t['key'] not in added:continue
                        curves.append(dict(case=case,method=name,arm=arm,component=t['key'],norad=row['candidate_norad'],
                            times=t['times'],residual_hz=c['conditional_residual_hz'][sl],
                            nominal_sigma_hz=p.point_noise[sl],points=len(t['times'])))
    write(OUT/'evidence/endpoint_audit.json',dict(rows=audits,maximum_objective_difference=max(abs(r['objective_difference']) for r in audits),
        original_12_frozen_source_hashes_match=True,source_sha256=sha(Path(__file__)),no_new_optimization=True))
    write(OUT/'evidence/gate_diagnostics.json',gate_records);write(OUT/'evidence/curve_residuals.json',curves)
    print('Replayed',len(audits),'fixed endpoints; max difference',max(abs(r['objective_difference']) for r in audits))
    for r in gate_records:
        if r['case'] in CASES[:3] and r['arm']=='fitted_c':print(r['case'],r['method'],r['worst_slacks'][:2])


if __name__=='__main__':main()
