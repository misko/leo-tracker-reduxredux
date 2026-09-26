"""Check refined CFO/LOS interpolation against fresh direct propagation."""
from pathlib import Path
import json
import numpy as np
from scipy.interpolate import CubicSpline
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
import timing_trial as trial

HERE=Path(__file__).resolve().parent

def main():
    rng=np.random.default_rng(20261005);taus=np.unique(np.r_[[-119.975,-.075,-.025,.025,.075,119.975],rng.integers(-4799,4800,25)*.025]);output=[]
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        for sid in ('scan-fw-f7515a5fdb02cda5','scan-fw-888fc1e1e005ded3'):
            p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')));membership=json.loads((HERE/'timing-trial'/f'{sid}-f1-q65-b161-membership.json').read_text());tracks={t.track_id:t for t in p.tracks}
            for fold in (0,1):
                prior=json.loads((HERE/'timing-trial'/f'{sid}-f{fold}-q33.json').read_text());assert p.evidence_sha256==prior['evidence_sha256'] and p.snapshot_digest==prior['snapshot_digest'];site=prior['protocol']['site'];times=np.array([r['time_s'] for r in prior['observations']])
                trial.T.FOLD=fold;trial.T.PARTITION_OVERRIDES[sid]={int(b):bool(m) for b,m in zip(trial.T.visit_bins(sid,times),prior['phase_training_mask'])}
                receiver,_,axis=trial.T.site_vectors(site)
                for rawtid,m in zip(prior['track_ids'],membership['tracks']):
                    assert rawtid==m['track_id'];track=tracks[m['equivalent_in_production_input'][0]];bank=dict(np.load(HERE/'timing-trial'/f'{sid}-f{fold}-{rawtid[7:19]}.npz'))
                    valid,_,tr,he=trial.residuals(p,track,site,bank['indices'],taus);assert np.array_equal(valid,bank['indices'])
                    predicted_tr=CubicSpline(bank['taus'],bank['train_residual'],axis=1)(taus);predicted_he=CubicSpline(bank['taus'],bank['held_residual'],axis=1)(taus)
                    position,_,valid=propagate_candidate_states(p.catalogue,bank['indices'],p.start_utc_ns,times,taus);assert np.array_equal(valid,bank['indices']);dr=position-receiver;projection=(dr/np.linalg.norm(dr,axis=-1)[...,None])@axis;approx=CubicSpline(bank['taus'],bank['projection'],axis=1)(taus)
                    result=dict(session_id=sid,fold=fold,track_id=rawtid,candidates=len(valid),offsets=len(taus),max_train_error_hz=float(np.max(abs(tr-predicted_tr))),max_held_error_hz=float(np.max(abs(he-predicted_he))),max_projection_error=float(np.max(abs(projection-approx))))
                    output.append(result);print(result,flush=True)
    finally:store.close()
    (HERE/'cfo-scale-mixture/interpolation-audit.json').write_text(json.dumps(dict(seed=20261005,taus_s=taus.tolist(),comparisons=output),indent=2)+'\n')

if __name__=='__main__':main()
