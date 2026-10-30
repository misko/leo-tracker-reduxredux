"""Check common residual structure across same-receiver satellite tracks."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


def common_screen(diagnostics,tracks):
    if len(diagnostics)!=len(tracks) or len(tracks)<2:raise ValueError('multiple matching tracks required')
    if len({t['receiver'] for t in tracks})!=1:raise ValueError('this audit pools one receiver at a time')
    ids=[o for t in tracks for o in t['observation_ids']]
    if len(ids)!=len(set(ids)):raise ValueError('common screen would duplicate observations')
    times=[];raw=[];normalized=[]
    for d,t in zip(diagnostics,tracks,strict=True):
        np.testing.assert_array_equal(d['times_s'],t['times'])
        r=np.asarray(d['raw_residual_hz'])-d['profile_bias_hz'];times.extend(t['times']);raw.extend(r);normalized.extend(r/(t['rf_hz']/11.5e9))
    times=np.asarray(times);order=np.argsort(times,kind='stable');times=times[order]
    if np.any(np.diff(times)<=0):raise ValueError('distinct timestamps required for pooled serial-correlation check')
    result=[]
    for name,values in [('Hz',raw),('RF_normalized',normalized)]:
        r=np.asarray(values)[order]
        noise={k:v[0].item() for k,v in batch_noise_screen(r[None],times).items()}
        result.append(dict(units=name,points=len(r),times_s=times,residual_hz=r,RMS_hz=float(np.sqrt(np.mean(r*r))),noise=noise,passed=noise['noise_screen_pass']))
    return result


def run(args):
    pr=read(args.trial/'protocol.json');a=read(args.trial/'new_family.json');c=read(args.trial/'control.json');replay=read(args.trial/'exact_owner_replay.json')
    path=Path(pr['job']['root'])/pr['job']['case']/'tracks.json';original=read(path);targets=pr['targets']
    tracks=[original[t['track_index']] for t in targets]
    for entry,t in zip(targets,tracks,strict=True):
        if entry['observation_ids']!=t['observation_ids']:raise ValueError('target authority mismatch')
    if len({t['receiver'] for t in tracks})!=1:raise ValueError('this bounded audit requires one receiver')
    rows=[]
    for row in replay['rows']:
        if row['role']!='new_family':continue
        for kind in ('target','continuous_target'):
            for result in common_screen(row[kind]['diagnostics'],tracks):rows.append(dict(arm=row['arm'],prediction=kind,**result))
    if len(rows)!=8:raise ValueError('both c arms and nominal/continuous predictions required')
    raw_pass=c['paired_valid'] and a['paired_valid'] and replay['all_verified'];passed=all(r['passed'] for r in rows)
    paths=[args.trial/n for n in ('protocol.json','control.json','new_family.json','exact_owner_replay.json')]+[path]
    write(args.output,dict(job=pr['job'],rows=rows,original_joint_gate_pass=raw_pass,common_residual_pass=passed,
        reviewed_joint_candidate=raw_pass and passed,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        no_refit=True,no_new_track_bias=True,no_GPS_selection=True,production_unchanged=True,
        caveat='additional common-structure diagnostic; correlated channels mean this is not a calibrated family-wise false-alarm probability'))
    print(pr['job']['label'],'raw',raw_pass,'common',passed,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('trial','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
