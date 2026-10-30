"""Post-fit member veto for soft satellite mixtures, without changing fits."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def member_checks(component,membership,members):
    if len(component['diagnostics'])!=1:raise ValueError('one union diagnostic required')
    d=component['diagnostics'][0];t=np.asarray(d['times_s']);r=np.asarray(d['raw_residual_hz'])-d['profile_bias_hz'];groups=np.asarray(membership)
    if groups.shape!=t.shape or groups.shape!=r.shape or set(groups.tolist())!=set(range(len(members))):raise ValueError('complete member geometry required')
    checks=[]
    for k,member in enumerate(members):
        keep=groups==k;times=t[keep];residual=r[keep];n=int(keep.sum())
        if n<4:checks.append(dict(member=member['track_id'],points=n,passed=False,reason='insufficient_member_points'));continue
        noise={name:value[0].item() for name,value in batch_noise_screen(residual[None],times).items()}
        rms=float(np.sqrt(np.mean(residual**2)));passed=bool(noise['noise_screen_pass'] and rms<=450)
        checks.append(dict(member=member['track_id'],points=n,RMS_hz=rms,noise=noise,passed=passed,
            same_bundle_bias_no_member_refit=True,times_s=times,residual_hz=residual))
    return checks


def run(args):
    pr=read(args.trial/'protocol.json');result=read(args.trial/'result.json');soft=read(args.trial/'soft_mixture.json');rows=[]
    for arm,v in soft['arms'].items():
        for kind,detail in [('nominal',v['mixture']),('exact_target',v['exact_target_components'])]:
            components=[]
            for c in detail['components']:
                checks=member_checks(c,pr['target']['member_indices'],pr['target']['members'])
                passed=all(r['passed'] for r in checks) and all(g['compatible'] for g in c['gates']) and c['phase_boundary_mass']<.01
                components.append(dict(norad=c['entry']['norad'],alias=c['entry']['alias'],weight=c['weight'],kind=c['kind'],checks=checks,passed=passed))
            mass=sum(c['weight'] for c in components if c['passed'])
            rows.append(dict(arm=arm,kind=kind,compatible_member_mass=mass,passes=mass>=.99,components=components))
    write(args.output,dict(rows=rows,qualified_soft_research_candidate=result['qualified_soft_research_candidate'] and all(r['passes'] for r in rows),
        original_whole_bundle_qualification=result['qualified_soft_research_candidate'],source_hashes={str(args.trial/name):hashlib.sha256((args.trial/name).read_bytes()).hexdigest() for name in ('protocol.json','result.json','soft_mixture.json')},
        no_refit=True,hard_identity_assigned=False,no_hard_association_credit=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trial','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
