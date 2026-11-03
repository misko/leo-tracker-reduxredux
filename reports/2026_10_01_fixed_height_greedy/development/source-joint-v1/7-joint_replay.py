"""Refit complete scans from blind spatial proposals with shared nuisances."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.append(str(HERE.parent/'2026_09_30_broad_prior_acquisition'))
from common import load_scan, digest, seal, source_bindings
from geoid import load_height_model
from orbit_input import use_extended_orbits
from physics_fixed import build_fixed_height_factor
from acquire import FixedHeightTrackLikelihood, propose
from leo.analysis.greedy_joint_location import fit_joint_greedy


def main(unit,output,proposal_path=None,seed_limit=3):
    start=time.monotonic()
    output=Path(output)
    if output.exists(): raise FileExistsError(output)
    scan=use_extended_orbits(load_scan(unit))
    height=load_height_model()
    sources=[HERE/p for p in ('joint_replay.py','physics_fixed.py','geoid.py','orbit_input.py','acquire.py','PROTOCOL.md')]
    sources += [ROOT/'src/leo/analysis/greedy_joint_location.py',
                HERE.parent/'2026_09_30_broad_prior_acquisition/spatial/rf.py']
    receipt={'schema':'fixed-height-joint-greedy/v1','unit_id':unit,'status':'running',
        'source_sha256':source_bindings(sources),'inputs':scan.inputs,
        'height_input_bindings':height.input_bindings,'height_msl_m':30.48,
        'qualification':'hard-association local mode search; no calibrated posterior claim',
        'prior':'uniform Sacramento250km disk; clock sigma1s, RXdrift and satelliteepoch sigma0.5',
        'seed_limit':seed_limit,'planned_factors':len(scan.tracks),'fits':[]}
    try:
        if proposal_path:
            proposal_path=Path(proposal_path)
            proposal=json.loads(proposal_path.read_text())
            if proposal.get('unit_id')!=unit or proposal.get('session_id')!=scan.session_id:
                raise ValueError('proposal recording mismatch')
            proposal_seal=json.loads(proposal_path.with_suffix('.seal.json').read_text())
            if proposal_seal['prediction_sha256']!=digest(proposal_path):
                raise ValueError('proposal seal mismatch')
            receipt['proposal_binding']={'path':str(proposal_path),'sha256':digest(proposal_path)}
            seeds=proposal.get('proposal',proposal)['seeds']
        else:
            proposal=asdict(propose(scan,height,max_tracks=8,deadline_s=40.))
            receipt['proposal']=proposal
            seeds=proposal['seeds']
        factors=[build_fixed_height_factor(obs,scan.bank,scan.layout,scan.config,height).factor for _,obs in scan.tracks]
        ports=[FixedHeightTrackLikelihood(obs,scan.bank,scan.config,height) for _,obs in scan.tracks]
        scores=[port.branch_loglik_at_state for port in ports]
        precision=np.r_[0.,0.,1.,np.full(scan.layout.dimension-4,4.)]
        for seed in seeds[:seed_limit]:
            if time.monotonic()-start > 80: break
            x=np.zeros(scan.layout.dimension-1)
            x[:2]=seed['east_km'],seed['north_km']
            result=fit_joint_greedy(x,factors,scores,precision,
                lambda state: bool(np.linalg.norm(state[:2]) <= 250.),
                max_iterations=24,deadline=start+85.)
            fit={'mean':result.mean[:5].tolist(),'satellite_epoch_s':result.mean[5:].tolist(),
                'associations':[str(scan.bank.norad_ids[i]) if i<len(scan.bank.norad_ids) else 'background'
                                for i in result.associations],
                'objectives':list(result.objectives),'converged':result.converged,
                'iterations':result.iterations,'reason':result.reason,
                'seed':seed,'seconds':time.monotonic()-start}
            receipt['fits'].append(fit)
            output.parent.mkdir(parents=True,exist_ok=True)
            output.with_suffix('.progress.json').write_text(json.dumps(receipt,allow_nan=False))
        completed=[f for f in receipt['fits'] if f['converged']]
        if completed:
            receipt['best']=min(completed,key=lambda f:f['objectives'][-1])
            receipt['status']='converged_local_mode'
        else:
            receipt['status']='unresolved'
    except Exception as error:
        receipt.update(status='error',exception={'type':type(error).__name__,'message':str(error)})
    receipt['wall_seconds']=time.monotonic()-start
    seal(output,receipt)
    print(json.dumps({k:receipt[k] for k in ('unit_id','status','wall_seconds')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('unit');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--proposal',type=Path);p.add_argument('--seed-limit',type=int,default=3)
    a=p.parse_args();main(a.unit,a.output,a.proposal,a.seed_limit)
