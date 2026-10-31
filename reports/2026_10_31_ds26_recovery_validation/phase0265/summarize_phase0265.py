"""Report sealed reference comparisons; known coordinates enter only here."""
import argparse
import hashlib
import json
from pathlib import Path
import math


def read(path): return json.loads(path.read_text())


def distance_km(latlon):
    # Reporting-only reference supplied after inference; never imported by fits.
    known=(37.849061591561885, -122.48574968092912)
    a,b,c,d=map(math.radians, (*known,*latlon))
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371.0088*2*math.asin(min(1., math.sqrt(h)))


def run(root):
    terminal=read(root/'terminal.json')
    if not terminal.get('completed'): raise ValueError('inference not completed')
    result=dict(reporting_only=True, GPS_used_for_inference=False, terminal=terminal,
        annotation=[], inclusion=[], recovery_claim=False)
    annotation_root=Path(read(root/'protocol.json').get('annotation_only_source',root))
    for limit in (15,30):
        ann=read(annotation_root/f'reference{limit}'/'annotation/result.json')
        for fold in ann['folds']:
            ordered={a:sorted(fold['proposals'],key=lambda q:q['arms'][a]['scores']['conditional_target']['negative_twice_log_density']) for a in ('c0','fitted_c')}
            for arm, proposals in ordered.items():
                best=proposals[0]; v=best['arms'][arm]; score=v['scores']['conditional_target']
                result['annotation'].append(dict(reference_limit_s=limit, seed=fold['seed'], arm=arm, norad=best['norad'],
                    RMS_hz=score['rms_hz'], score=score['negative_twice_log_density'],
                    final_phase_change_s=v['final_phase_change_s'], target_phase_mean_s=v['target_phase_training_mean_s'],
                    target_phase_boundary_mass=v['target_phase_boundary_mass'], mask_sha256=v['mask_sha256'],
                    position_error_km=distance_km(__import__('prototype_dsx01_continuous_position').latlon(v['endpoint_east_north_km'])),
                    optimizer_stopped=[h['optimizer'].get('stopped') for h in v['history']],
                    minimum_bank_margin_s=min((h['next_reference_domain']['minimum_margin_s']
                        for h in v['history'] if 'next_reference_domain' in h),default=None)))
        if not terminal.get('inclusion_attempted'): continue
        folder=root/f'reference{limit}'/'inclusion'; audit=read(folder/'exact_owner_replay.json')
        for role in ('control','target_0'):
            saved=read(folder/(role+'.json'))
            for arm,v in saved['arms'].items():
                check=next(r for r in audit['rows'] if r['role']==role and r['arm']==arm)
                result['inclusion'].append(dict(reference_limit_s=limit,role=role,arm=arm,
                    paired_valid=saved['paired_valid'], exact_owner_verified=check['verified'],
                    RMS_hz=v['RMS_hz'], objective=v['negative_twice_elbo'],
                    endpoint_east_north_km=v['endpoint_east_north_km'],position_error_km=distance_km(v['endpoint_latlon']),
                    associated_points=len(v['proposed_associated_ids']),added_points=v['added_points'],lost_points=v['lost_points'],
                    final_phase_change_s=v['final_phase_change_s'],
                    optimizer_stopped=[h['fit'].get('stopped') for h in v['history']],
                    optimizer_evaluations=[h['fit'].get('evaluations') for h in v['history']],
                    failed_curved=[g['component'] for g in v['gates']['tracks'] if not g['compatible']],
                    failed_predictive=[g['component'] for g in v['linear_gates'] if not g['compatible']],
                    incumbent_owner_changes=len(check['incumbent_ownership_changes']), control_owner_changes=len(check['control_ownership_changes']),
                    exact_failed_families=[g['norad'] for g in check['exact_family_replays'] if not g['all_pass']],
                    exact_replay_failure_note='Each family replacement reruns global gates; failure does not identify that family as bad.',
                    target_exact_negative_slacks={k:s for q in check['exact_family_replays'] if q['norad']==66102
                        for k,s in q['all_gate_slacks'].items() if s<0},
                    maximum_exact_orbit_difference_hz=max(g['maximum_linearization_difference_hz'] for g in check['exact_family_replays']),
                    target_RMS_hz=[g['RMS_hz'] for g in v.get('target_diagnostics',[])],
                    target_gates=v.get('targets')))
    # Masks and candidate competitions must match across numerical references.
    rows=result['annotation']; groups={(r['seed'],r['arm']) for r in rows}
    result['all_masks_match']=all(next(r for r in rows if r['reference_limit_s']==15 and (r['seed'],r['arm'])==key)['mask_sha256']==
        next(r for r in rows if r['reference_limit_s']==30 and (r['seed'],r['arm'])==key)['mask_sha256'] for key in groups)
    if terminal.get('inclusion_attempted'):
        seal=read(root/'inference_seal.json')
        result['inference_seal_valid']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in seal['artifacts_sha256'].items())
        addition=[r for r in result['inclusion'] if r['reference_limit_s']==30 and r['role']=='target_0']
        control=[r for r in result['inclusion'] if r['reference_limit_s']==30 and r['role']=='control']
        result['recovery_claim']=bool(len(addition)==2 and all(r['paired_valid'] and r['exact_owner_verified'] for r in addition+control))
    (root/'reporting_summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); run(parser.parse_args().root)
