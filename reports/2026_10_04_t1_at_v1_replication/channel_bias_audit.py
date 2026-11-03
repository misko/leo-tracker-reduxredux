"""Full-cohort residual diagnostic at saved estimated positions, not at the roof.

Estimate shared RX/channel offsets after projecting out a separate quadratic
for each satellite/RX track. This is an in-sample diagnostic, not a localization
correction or independent identity validation. Both RF arms are inspected.
"""
import csv
import json
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load,HERE
from subset_positions import enable_research_model,serial
from timing_bound_comparison import digest

enable_research_model()
from rf_calibration_diagnostic import CalibrationObjective

SOURCE=HERE/'timing-bound-10s-vs-20s/cross-start-polish'
OUT=HERE/'channel-bias-audit'
SCANS=tuple(f'N{i:02}' for i in range(1,17))
ARMS=('fitted-c','zero-c')


def channel_basis(rf,receiver,channel):
    """Five contrasts orthogonal to both RX offsets and the shared RF slope.

Use equal lane weighting to define a fixed physical parametrization; the fit
itself uses observation weights. c=0 removes the shared RF slope without letting
the added contrasts recreate it. Different numbers of windows do not change
these constraints. Every lane must have one constant RF in the input scan.
"""
    rf,receiver,channel=map(np.asarray,(rf,receiver,channel))
    if not (rf.shape==receiver.shape==channel.shape) or rf.ndim!=1:
        raise ValueError('Mismatched input vectors')
    if not np.all(np.isin(receiver,[0,1])) or not np.all(np.isin(channel,[1,2,3,4])):
        raise ValueError('Unexpected receiver/channel')
    lanes=4*receiver.astype(int)+channel.astype(int)-1
    frequencies=[]
    for lane in range(8):
        values=np.unique(rf[lanes==lane])
        if len(values)!=1:raise ValueError('Each lane requires one known RF')
        frequencies.append(values[0])
    frequencies=np.asarray(frequencies)
    constraints=np.vstack([np.repeat([1.,0.],4),np.repeat([0.,1.],4),
                           (frequencies-frequencies.mean())/1e9])
    _,singular,vh=np.linalg.svd(constraints,full_matrices=True)
    if min(singular)<1e-8:raise ValueError('Degenerate RF contrast')
    basis=vh[3:].T
    np.testing.assert_allclose(constraints@basis,0.,atol=1e-12)
    return basis[lanes],basis,frequencies


def controlled_channel_fit(times,residual,tracks,features,sigma=50.):
    """Residualize per-track quadratics, then fit zero-centered ridge offsets."""
    times,residual,tracks,features=map(np.asarray,(times,residual,tracks,features))
    if not len(times) or not (len(times)==len(residual)==len(tracks)==len(features)):
        raise ValueError('Nonempty matched diagnostic inputs required')
    residualized=np.zeros_like(residual,dtype=float);x=np.zeros_like(features)
    rank=0
    for track in np.unique(tracks):
        mask=tracks==track
        t=times[mask]-np.mean(times[mask]);t/=max(1.,np.max(abs(t)))
        z=np.column_stack([np.ones(sum(mask)),t,t*t])
        _,_,r,_=np.linalg.lstsq(z,residual[mask],rcond=None);rank+=r
        residualized[mask]=residual[mask]-z@np.linalg.lstsq(z,residual[mask],rcond=None)[0]
        x[mask]=features[mask]-z@np.linalg.lstsq(z,features[mask],rcond=None)[0]
    normal=x.T@x/200.**2+np.eye(x.shape[1])/sigma**2
    coefficient=np.linalg.solve(normal,x.T@residualized/200.**2)
    remaining=residualized-x@coefficient
    return dict(coefficients=coefficient,controlled_rms_hz=np.sqrt(np.mean(residualized**2)),
                channel_corrected_rms_hz=np.sqrt(np.mean(remaining**2)),
                control_rank=rank,channel_design_eigenvalues=np.linalg.eigvalsh(x.T@x/200.**2),
                residualized=residualized,remaining=remaining)


def run():
    OUT.mkdir(exist_ok=True)
    rows=[];lanes=[];details={}
    for scan in SCANS:
        data,meta,_=load(scan)
        features,basis,frequencies=channel_basis(data.rf,data.receiver,data.channel)
        owner=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in data.owners])
        for arm in ARMS:
            path=SOURCE/f'{scan}-{arm}-20s.json';saved=json.loads(path.read_text());best=saved['best']
            assert saved['input_sha256']==meta['input_sha256']
            obj=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
            obj.features=((data.rf-meta['rf_center_hz'])/1e9)[:,None];obj.likelihood.features=obj.features
            obj.base.minimum_shift_s=max(obj.base.minimum_shift_s,-20.)
            obj.base.maximum_shift_s=min(obj.base.maximum_shift_s,20.)
            obj.base.deadline=float('inf')
            if arm=='zero-c':obj.bounds[-1]=(0.,0.)
            v=np.asarray(best['vector']);score,_=obj.evaluate(v)
            assert abs(score-best['objective'])<1e-7
            probability=obj.likelihood.last_result['row_association_probability']
            pred,visible=obj.base.predict(v[:obj.size]);pred+=obj.features@v[obj.size:,None]
            alias=obj.likelihood.alias_hz
            residual=(data.measured-pred[np.arange(len(owner)),owner]+alias/2)%alias-alias/2
            owner_probability=probability[np.arange(len(owner)),owner]
            conditional_identity=owner_probability/np.maximum(probability.sum(axis=1),1e-300)
            # Presence and identity are different questions. The old .8 joint
            # probability gate is unattainable for a 50-satellite bank even at
            # zero residual. Require signal support plus unambiguous identity.
            good=(owner_probability>=.5)&(conditional_identity>=.9)&visible[np.arange(len(owner)),owner]&(abs(residual)<=600.)
            track=data.owners*2+data.receiver
            fit=controlled_channel_fit(data.times[good],residual[good],track[good],features[good])
            offsets=basis@fit['coefficients']
            row=dict(scan=scan,arm=arm,windows=len(owner),supported_windows=int(sum(good)),
                location_error_m=saved['distance_m'],location_converged=saved['converged'],
                baseline_rms_hz=np.sqrt(np.mean(residual[good]**2)),
                quadratic_controlled_rms_hz=fit['controlled_rms_hz'],
                plus_channel_rms_hz=fit['channel_corrected_rms_hz'],
                channel_rms_reduction_percent=100*(1-fit['channel_corrected_rms_hz']/fit['controlled_rms_hz']),
                channel_offset_rms_hz=np.sqrt(np.mean(offsets**2)),channel_offset_peak_to_peak_hz=np.ptp(offsets),
                weakest_channel_information=float(min(fit['channel_design_eigenvalues'])))
            rows.append(row)
            for lane in range(8):
                rx,ch=divmod(lane,4);mask=good&(data.receiver==rx)&(data.channel==ch+1)
                lanes.append(dict(scan=scan,arm=arm,receiver=rx,channel=ch+1,rf_hz=frequencies[lane],
                    correction_hz=offsets[lane],supported_windows=int(sum(mask)),satellites=len(set(data.owners[mask]))))
            details[f'{scan}-{arm}']=dict(source=str(path),source_sha256=digest(path),input_sha256=meta['input_sha256'],
                fit_original_rows=data.original_rows[good],heldout_original_rows=[],basis=basis,
                coefficients=fit['coefficients'],channel_design_eigenvalues=fit['channel_design_eigenvalues'],
                diagnostic_scope='Saved estimated position; original-owner probability >=.5, conditional identity >=.9, visible and <=600 Hz; per-track/RX quadratics projected out.')
            print('CHANNEL AUDIT',scan,arm,'RMS',round(row['quadratic_controlled_rms_hz'],1),'to',round(row['plus_channel_rms_hz'],1),
                  'offset range',round(row['channel_offset_peak_to_peak_hz'],1),flush=True)
    for name,values in [('summary.csv',rows),('lane-offsets.csv',lanes)]:
        with (OUT/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    (OUT/'audit.json').write_text(json.dumps(dict(scope=__doc__,priors_sigma_hz=50.,details=details),default=serial,indent=2,allow_nan=False))
    render(rows,lanes)


def render(rows,lanes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,8),sharey=True)
    maximum=max(abs(r['correction_hz']) for r in lanes)
    for ax,arm in zip(axes,ARMS):
        matrix=np.array([[next(r['correction_hz'] for r in lanes if (r['scan'],r['arm'],r['receiver'],r['channel'])==(s,arm,rx,ch))
                          for rx in (0,1) for ch in (1,2,3,4)] for s in SCANS])
        im=ax.imshow(matrix,cmap='RdBu_r',vmin=-maximum,vmax=maximum,aspect='auto')
        for i in range(16):
            for j in range(8):ax.text(j,i,f'{matrix[i,j]:+.0f}',ha='center',va='center',fontsize=8,color='white' if abs(matrix[i,j])>.6*maximum else 'black')
        ax.set_xticks(range(8),[f'RX{rx}\nCH{ch}' for rx in (0,1) for ch in (1,2,3,4)])
        ax.set_yticks(range(16),SCANS);ax.set_title('Fitted c' if arm=='fitted-c' else 'c = 0')
    fig.suptitle('Do channel-specific residual biases survive per-track quadratic controls?',fontsize=17)
    fig.colorbar(im,ax=axes,shrink=.8,label='Estimated additional lane correction (Hz)')
    fig.subplots_adjust(top=.9,bottom=.15,right=.82,wspace=.12)
    fig.text(.5,.035,'At saved estimated positions, using confidently matched original-owner windows. All retained rows fit and evaluated together.\n'
             'Five lane contrasts exclude both RX intercepts and the common RF slope; zero-centered 50 Hz prior.\n'
             'Diagnostic only: track quadratics are controls, not additions to the localization model. No evidence of identity correctness or held-out accuracy.',ha='center',fontsize=10)
    fig.savefig(OUT/'channel-biases.png',dpi=160);plt.close(fig)


if __name__=='__main__':run()
