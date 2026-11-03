"""Check shared non-affine pilot-frame innovations, not just common timing."""

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_shared_waveform import frame_positions,derangements
from local_pilot_refinement import pilot_wave
from probe_native_code_carrier import interpolate_periodic
from probe_ds23_frame_phase_coherence import coherence
from probe_ds23_0268_shared_waveform import OUT
from run_algo01_ds23_sample import ROOT,read,write,sha


def gains(samples,pair,fs):
    rows=[]
    for rx in (0,1):
        point=pair['receivers'][str(rx)]
        peak=point['peak']
        epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        offset=list(pair['receiver_ids']).index(rx)
        y=samples[:,offset,0].astype(float)+1j*samples[:,offset,1].astype(float)
        pos=frame_positions(len(y),fs,epoch)
        n=np.arange(len(y))
        frame=(np.interp(pos,n,y.real)+1j*np.interp(pos,n,y.imag))*np.exp(-2j*np.pi*peak['fractional_tracking_cfo_hz']*pos/fs)
        template=interpolate_periodic(pilot_wave(fs,point['probe']['edge']),(pos-epoch)*32)
        frame-=frame.mean(axis=1,keepdims=True)
        template-=template.mean(axis=1,keepdims=True)
        energy=np.sum(abs(template)**2,axis=1)
        gain=np.sum(template.conj()*frame,axis=1)/energy
        rows.append((pos.mean(axis=1)/fs,gain,energy))
    count=min(len(r[0]) for r in rows)
    return [(t[:count],g[:count],e[:count]) for t,g,e in rows]


def main():
    destination=OUT/'shared_frame_gain_diagnostic.json'
    if destination.exists():raise FileExistsError('preserve frame-gain diagnostic')
    rows=[]
    with np.load(OUT/'curved_pair_IQ.npz',allow_pickle=False) as z:
        metadata=json.loads(str(z['metadata_json']))
        for pair in metadata['pairs']:
            series=gains(z[f"window_{pair['visit_index']:06d}"],pair,metadata['sample_rate_hz'])
            first,second=[coherence(t,g,e) for t,g,e in series]
            t,g,e=series[0]
            ratio=series[1][1]*g.conj()
            relative=coherence(t,ratio,np.ones(len(t)))
            null=[]
            for permutation in derangements(len(t)):
                other=series[1][1][permutation]*g.conj()
                null.append(coherence(t,other,np.ones(len(t)))['phase_only_fraction'])
            amplitude=np.corrcoef(abs(g),abs(series[1][1]))[0,1]
            row=dict(visit_index=pair['visit_index'],single_RX1=first,single_RX2=second,relative=relative,
                amplitude_correlation=float(amplitude),shuffled_relative_phase_coherence=null,
                shared_nonlinear_phase_fingerprint=bool(first['phase_only_fraction']<.7 and second['phase_only_fraction']<.7
                    and relative['phase_only_fraction']>.9 and relative['phase_only_fraction']>max(null)),
                transmitter_identity_not_proven_by_affine_phase_coherence_alone=True)
            rows.append(row)
            print(row['visit_index'], 'single',[first['phase_only_fraction'],second['phase_only_fraction']],
                  'relative',relative['phase_only_fraction'],'null max',max(null),'amplitude',amplitude,flush=True)
    write(destination,dict(rows=rows,panel_sha256=sha(OUT/'curved_pair_IQ.npz'),
        source_sha256=sha(ROOT/'tools/diagnose_ds23_0268_shared_frame_gains.py'),
        no_GPS_TLE_or_position_used=True,no_calibration_or_identity_change_applied=True))
    fig,axes=plt.subplots(len(rows),1,figsize=(13,2.8*len(rows)),squeeze=False)
    for ax,row in zip(axes[:,0],rows,strict=True):
        for label,curve,color in [('RX1',row['single_RX1'],'#267b44'),('RX2',row['single_RX2'],'#9659ad'),
                                   ('RX2/RX1',row['relative'],'#277cce')]:
            ax.plot(np.asarray(curve['frame_time_s'])*1000,curve['residual_phase_rad'],'.-',label=label,color=color)
        ax.set_title(f"Visit {row['visit_index']} · shared nonlinear fingerprint: {row['shared_nonlinear_phase_fingerprint']}")
        ax.set(xlabel='Time in recorded probe (ms)',ylabel='Affine-removed phase (rad)')
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'frame_gain_innovations.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
