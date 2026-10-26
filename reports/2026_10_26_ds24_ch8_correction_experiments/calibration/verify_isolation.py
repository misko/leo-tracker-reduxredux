"""Adversarial held-value control: training cannot depend on CH8 response values."""
import json
import numpy as np
from run import ROOT, OUT, native_scan, write
import algo02_scan as algo
from probe_ds23_graph_seeded_paths import build

rows=[]
for case in ('DS24-0010','DS24-0011'):
    saved=json.loads((ROOT/'family_cavity/position'/f'{case}.json').read_text())
    selected=saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(ROOT); scan=algo.load_scan(ROOT,case)
    d=dict(scan=scan,node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),model=saved['model'],
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'])
    sample=build(d,'default','c0',np.zeros(len(d['means'])))
    ch=np.concatenate([np.full(sl.stop-sl.start,scan.tracks[i]['channel'])
                       for i,sl in zip(sample.members,sample.slices,strict=True)])
    held=d['keep'] & (ch==8)
    train=d['keep'] & (ch!=8)
    entries=[e for e in d['entries'] if scan.tracks[e['track_index']]['channel']!=8]
    for arm in ('c0','fitted_c'):
        record=json.loads((OUT/f'{case}_{arm}.json').read_text())
        for variant in ('RF_scaled','native_Hz'):
            state=record['results'][variant]
            problem_data=dict(d,keep=train,entries=entries,
                              scan=scan if variant=='RF_scaled' else native_scan(scan))
            p=build(problem_data,'default',arm,state['phase_reference'])
            altered=build(problem_data,'default',arm,state['phase_reference'])
            altered.values=altered.values.copy()
            altered.values[held]+=100000*np.sin(np.arange(held.sum())+1)
            position=np.asarray(state['endpoint_east_north_km'])
            a=p.calculate(position);b=altered.calculate(position)
            delta=float(b['negative_twice_elbo']-a['negative_twice_elbo'])
            coefficient=float(np.max(abs(a['coefficient']-b['coefficient'])))
            assert delta==0 and coefficient==0
            rows.append(dict(case=case,arm=arm,variant=variant,training_objective_delta=delta,
                             maximum_coefficient_change=coefficient,held_perturbation_amplitude_hz=100000))
write(OUT/'held_response_isolation.json',dict(rows=rows,all_passed=True,
    interpretation='CH8 responses cannot update the trained objective or coefficients under fixed conditioning metadata.',
    independent_identity_validation=False,GPS_used=False))
print('All eight held-response isolation checks passed')
