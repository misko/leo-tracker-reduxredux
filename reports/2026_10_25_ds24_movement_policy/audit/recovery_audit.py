"""Independent saved recovery decisions and fixed-position model replay; no GPS/refits."""
import hashlib
import json
from pathlib import Path

import numpy as np

from matched_controls import load_baseline
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_active_mode_support import make_problem
from probe_ds23_frequency_events import cached, summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay
from run_ds23_combined_recovery_full import valid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RECOVERY = ROOT/'recovery'
ARMS = ('c0','fitted_c')
CASES = ('DS24-0095','DS24-0087')


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_seal(directory):
    seal = read(directory/'scientific_seal.json')
    for name,digest in seal['files'].items():
        assert sha(directory/name) == digest, name
    return sha(directory/'scientific_seal.json')


def build(d, trial, arm, saved, kind, protected):
    keep=np.asarray(trial['mask'],bool)
    arguments=(d['scan'],trial['node'],keep,arm,np.asarray(saved['phase_reference']),
               d['powers'],np.asarray(trial['means']),d['model'])
    if kind=='support':p=make_problem(*arguments,set(protected))
    else:p=make_event_problem(*arguments,[])
    attach_event_predictive(p,trial['entries'],d['powers'])
    return cached(p)


def replay(d, trial, arm, saved, kind, protected):
    p=build(d,trial,arm,saved,kind,protected)
    x=np.asarray(saved['endpoint_east_north_km'])
    got=summary(p,x,trial['entries']);c=p.calculate(x)
    objective=abs(got['negative_twice_elbo']-saved['negative_twice_elbo'])
    rms=abs(got['RMS_hz']-saved['RMS_hz'])
    assert objective < 1e-5 and rms < 1e-5, (kind,arm,objective,rms)
    assert_curved_gate_replay(saved['gates'],got['gates'])
    for a,b in zip(saved.get('linear_gates',[]),got.get('linear_gates',[]),strict=True):
        for key in ('component','compatible','points','observation_ids'):
            assert a[key]==b[key]
    if 'coefficient' in saved:np.testing.assert_allclose(saved['coefficient'],c['coefficient'],rtol=1e-10,atol=1e-8)
    disabled=getattr(p,'disabled_new_one_owner_orbit_families',[])
    if kind=='support':
        raw=build(d,trial,arm,saved,'graph',protected)
        owners={}
        for row,i,sl in zip(raw.rows,raw.members,raw.slices,strict=True):
            if raw.keep[sl].any():
                owners.setdefault(row['candidate_index'],set()).add((d['scan'].tracks[i]['receiver'],d['scan'].tracks[i]['channel']))
        expected=[j for j in raw.supported if j not in protected and len(owners.get(j,()))==1]
        assert disabled==expected
        assert all(j not in protected and j in owners for j in disabled)
    return dict(objective_difference=objective,RMS_difference_hz=rms,
        final_log_precision_change=float(c['final_log_precision_change']),
        supported=[int(j) for j in p.supported],disabled_new_active_one_owner=[int(j) for j in disabled])


def trial_checks(d,parent,trial,kind):
    protected=set(parent['original_protected'])
    original_keep=np.asarray(parent['mask'],bool)
    assert np.all(np.asarray(trial['mask'],bool)[original_keep])
    assert trial['entries']==parent['entries']
    assert trial['added_curved_points']==int(np.sum(trial['mask'])-np.sum(original_keep))
    records=[];preserved=True
    final={}
    for arm in ARMS:
        final[arm]=replay(d,trial,arm,trial['arms'][arm],kind,protected)
        records.append(dict(arm=arm,version='final',**final[arm]))
        if 'ordinary_arms' in trial:
            records.append(dict(arm=arm,version='ordinary',**replay(d,trial,arm,trial['ordinary_arms'][arm],'graph',protected)))
        coverage=trial['coverage'][arm]
        preserved &= set(parent['coverage'][arm]['accepted_observation_ids'])<=set(coverage['accepted_observation_ids'])
        preserved &= set(parent['coverage'][arm]['curved_observation_ids'])<=set(coverage['curved_observation_ids'])
        preserved &= set(parent['coverage'][arm]['predictive_observation_ids'])<=set(coverage['predictive_observation_ids'])
        required=set(parent['coverage'][arm]['supported_families'])&protected
        preserved &= required<=set(final[arm]['supported'])
        if kind=='graph':preserved &= set(parent['coverage'][arm]['supported_families'])<=set(final[arm]['supported'])
        assert set(final[arm]['supported'])==set(coverage['supported_families'])
    gate_valid=bool(valid(trial['arms']) and all(trial['arms'][a]['final_phase_change_s']<=.01 for a in ARMS))
    assert gate_valid==trial['paired_valid']
    if 'ordinary_arms' in trial:
        ordinary_valid=valid(trial['ordinary_arms'])
        minima=trial['minimum_slacks_before_rescue']
        rescue=(not ordinary_valid and bool(minima) and min(minima.values())>=-.25)
        assert rescue==trial['constrained_refinement_attempted']
    return records,gate_valid,bool(preserved)


def main():
    seals={name:verify_seal(RECOVERY/name) for name in ('','repair01','eligibility02')}
    protocol=read(RECOVERY/'protocol.json')
    for group in ('source_sha256','input_sha256'):
        for path,digest in protocol[group].items():assert sha(path)==digest,path
    rows=[];case_rows=[]
    for case in CASES:
        d=load_baseline(case);parent=read(RECOVERY/case/'parent.json')
        graph=read(RECOVERY/case/'graph/result.json')
        repaired=read(RECOVERY/'repair01'/case/'result.json')
        corrected=read(RECOVERY/'eligibility02'/case/'result.json')
        assert graph['status']==repaired['status']==corrected['status']=='complete'
        assert len(repaired['trials'])==len(corrected['trials'])<=2
        passing=[]
        for trial in graph['trials']:
            checks,valid_pair,preserved=trial_checks(d,parent,trial,'graph')
            assert trial['accepted']==(valid_pair and preserved)
            if valid_pair and preserved:passing.append(trial)
            rows.append(dict(case=case,branch='graph',trial_index=trial['trial_index'],paired_valid=valid_pair,
                accepted=trial['accepted'],added_curved_points=trial['added_curved_points'],checks=checks))
        expected=min(passing,key=lambda r:(-r['added_curved_points'],tuple(a['component'] for a in r['additions']),r['arms']['c0']['corrected_selection_loss'])) if passing else None
        assert graph['selected']==expected
        passing=[]
        for strict,trial in zip(repaired['trials'],corrected['trials'],strict=True):
            assert strict['arms']==trial['arms']
            assert strict['node']==trial['node'] and strict['mask']==trial['mask']
            assert strict['additions']==trial['additions']
            checks,valid_pair,preserved=trial_checks(d,parent,trial,'support')
            assert trial['accepted']==(valid_pair and preserved)
            assert trial['strict_original_layout_accepted']==strict['accepted']
            assert trial['strict_original_layout_preservation']==strict['preservation']
            if valid_pair and preserved:passing.append(trial)
            rows.append(dict(case=case,branch='support_active_incumbent_control',trial_index=trial['trial_index'],
                paired_valid=valid_pair,accepted=trial['accepted'],strict_original_accepted=strict['accepted'],
                added_curved_points=trial['added_curved_points'],checks=checks))
        expected=min(passing,key=lambda r:(-r['added_curved_points'],tuple(a['component'] for a in r['additions']))) if passing else None
        assert corrected['selected']==expected
        for record,selected in ((graph,graph['selected']),(repaired,repaired['selected']),(corrected,corrected['selected'])):
            assert record['policy_arms']==(selected['arms'] if selected else parent['arms'])
        case_rows.append(dict(case=case,graph_trials=len(graph['trials']),support_trials=len(corrected['trials']),
            graph_selected=graph['selected'] is not None,support_active_incumbent_selected=corrected['selected'] is not None,
            strict_support_selected=repaired['selected'] is not None,
            support_nominees=[] if expected is None else expected['additions']))
        print('independent recovery replay complete',case,flush=True)
    output=dict(status='passed',GPS_used=False,no_position_fits=True,source_sha256=sha(Path(__file__)),
        scientific_seals=seals,rows=rows,cases=case_rows,
        all_saved_original_and_rescued_graph_endpoints_replayed=True,
        all_support_trials_symmetrically_replayed=True,
        immutable_original_parent_protection=True,
        maximum_objective_difference=max(c['objective_difference'] for r in rows for c in r['checks']),
        no_geography_opened_before_scientific_seals=True,
        limitations=['Original preflight missed augmented-context support reconstruction; original stages failed closed and were preserved.',
            'Repair01 repeats only previously frozen support proposals whose first fitted pair was not persisted before failure, charging remaining original budgets.',
            'Eligibility02 reinterprets incumbent mode preservation as the original active curved/predictive set, with no refit and symmetric checks of all sealed support trials.'])
    with (HERE/'recovery_artifacts.json').open('x') as stream:
        json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
