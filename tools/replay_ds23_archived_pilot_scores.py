"""Verify archived GLRT scores, including the unpersisted acquired-CFO grid bin."""

import argparse
from pathlib import Path
import numpy as np
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
from probe_ds23_raw_pilot_refinement import OUT
from run_algo01_ds23_sample import read,write,sha

RESIDUAL_BIN_HZ=1/(512*OFDM_SYMBOL_DURATION_S)


def reconstruct(samples,fs,edge,peak):
    tracking=float(peak['fractional_tracking_cfo_hz']);trials=[]
    for k in (0,-1,1,-2,2):
        acquired=tracking-k*RESIDUAL_BIN_HZ
        result=conditioned_glrt64_score(samples,fs,epoch_sample=peak['integer_epoch_sample'],
            fractional_epoch_offset_samples=peak['fractional_epoch_offset_samples'],acquired_cfo_hz=acquired,edge=edge)
        errors=dict(exact=result.exact_score-peak['fractional_exact_score'],
                    control=result.control_score-peak['fractional_control_score'],tracking_hz=result.tracking_cfo_hz-tracking)
        trials.append(dict(bin=k,acquired_CFO_hz=acquired,errors=errors))
        if max(abs(errors['exact']),abs(errors['control']))<1e-10 and abs(errors['tracking_hz'])<1e-5:
            return dict(matched=True,selected=trials[-1],trials=trials)
    return dict(matched=False,trials=trials)


def run(case):
    path=OUT/(case+'_tracks.json');d=read(path);panel=OUT/(case+'_tracks_panel.npz')
    assert sha(panel)==d['panel_sha256'];z=np.load(panel,allow_pickle=False);rows=[]
    fs=d['panel_metadata']['sample_rate_hz']
    for row in d['rows']:
        p=row['point'];v=z[p['window_key']][:,p['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float)
        rows.append(dict(observation_id=p['observation_id'],result=reconstruct(y,fs,p['edge'],p['peak'])))
    write(OUT/(case+'_score_replay.json'),dict(case=case,rows=rows,matched=sum(r['result']['matched'] for r in rows),
        total=len(rows),residual_bin_hz=RESIDUAL_BIN_HZ,bins_tested=[0,-1,1,-2,2],
        raw_result_sha256=sha(path),panel_sha256=sha(panel),source_sha256=sha(Path(__file__)),
        reconstruction_is_RF_only_diagnostic_not_new_frequency_measurement=True))
    print(case,'exact score replay',sum(r['result']['matched'] for r in rows),'/',len(rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
