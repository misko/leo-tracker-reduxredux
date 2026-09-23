"""Summarize measured cross-rate evidence and explicitly illustrative geometry bounds."""
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent


def load(path):
    if path.exists():
        return json.loads(path.read_text())
    with gzip.open(str(path)+'.gz','rt') as handle:
        return json.load(handle)


def save(name,data):
    (ROOT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def median(values):
    values=[v for v in values if v is not None]
    return None if not values else float(np.median(values))


def line(ax,t,values,**kw):
    y=np.degrees(np.angle(np.exp(1j*np.asarray(values))))
    xs=[];ys=[]
    for i in range(len(y)):
        if i and abs(y[i]-y[i-1])>180:
            xs.append(np.nan);ys.append(np.nan)
        xs.append(t[i]);ys.append(y[i])
    ax.plot(xs,ys,**kw)


def run():
    selection=load(ROOT/'selection.json')
    matched=load(ROOT/'matched-duration.json')['rows']
    bymatched={(r['session_id'],r['visit']):r for r in matched}
    summary=[];details=[];examples=[];parity=[]
    for entry in selection:
        sid=entry['session_id'];inv=load(ROOT/sid/'inventory.json')
        original=ROOT.parent/'2026_09_23_scan_1aa_phase_methods' if sid=='scan-fw-1aa1d50103d97388' else ROOT/sid
        doc=load(original/'comparison.json')
        assert doc['selection']==entry['selected_visits']
        completed=[r for r in doc['visits'] if r['state']=='replayed']
        supported=[r for r in completed if r['production_relative_phase']['supported']]
        old={r['visit_index']:r for r in inv.get('existing_phase',[])}
        for r in completed:
            if r['visit'] in old:
                assert r['production_relative_phase']==old[r['visit']]['evidence'],(sid,r['visit'])
                parity.append([sid,r['visit']])
        mr=[r for r in matched if r['session_id']==sid]
        ms=[r for r in mr if r.get('supported')]
        start=inv['timing']['first_sample_estimate_utc_ns']
        record=dict(**entry,start_utc=datetime.fromtimestamp(start/1e9,timezone.utc).isoformat(),
            timestamp_half_bracket_s=inv['timing']['first_sample_bracket_width_ns']/2e9,
            existing_selected=len(old),existing_supported=sum(r['state']=='supported' for r in old.values()),
            native_completed=len(completed),native_supported=len(supported),
            native_supported_spline_rms_median_deg=median([r['curve_fits']['B_validation'][r['curve_fits']['selected']]['B_rms_deg'] for r in supported]),
            native_supported_pilot_rms_median_deg=median([r['production_relative_phase']['pilot_held_rms_deg'] for r in supported]),
            native_pilot_comparable_count=sum(r['production_relative_phase']['pilot_held_rms_deg'] is not None for r in supported),
            matched_supported=len(ms),matched_completed=sum(r['state']=='replayed' for r in mr),
            matched_supported_spline_rms_median_deg=median([r['curve_fits']['B_validation'][r['curve_fits']['selected']]['B_rms_deg'] for r in ms]),
            native_block_ms=4096/entry['sample_rate_hz']*1000,
            replay_elapsed_s=doc['elapsed_s'])
        summary.append(record)
        if entry['selected_visits']:
            # Display choice is fixed by detection priority, never phase quality.
            example=max(doc['visits'],key=lambda r:r['inventory']['priority'])
            examples.append((entry,example,bymatched[sid,example['visit']]))
        for r in doc['visits']:
            m=bymatched[sid,r['visit']]
            d=dict(session_id=sid,visit=r['visit'],sample_rate_msps=entry['sample_rate_hz']/1e6,
                   channel=r['inventory']['target']['channel'],native_state=r['state'],
                   native_supported=r.get('production_relative_phase',{}).get('supported',False),
                   matched_state=m['state'],matched_supported=m.get('supported',False))
            if r['state']=='replayed':
                p=r['production_relative_phase'];fit=r['curve_fits']
                d.update(native_coherence=p['tracked_coherence'],native_wrong_time=p['wrong_time_coherence'],
                    native_resultant=p['band_phase_resultant'],native_spline_rms_deg=fit['B_validation'][fit['selected']]['B_rms_deg'],
                    native_linear_rms_deg=fit['B_validation']['linear']['B_rms_deg'],native_pilot_rms_deg=p['pilot_held_rms_deg'],
                    pilot_held_count=p['pilot_held_count'],relative_cfo_hz=p['relative_cfo_hz'],
                    relative_cfo_rate_hz_s=p['relative_cfo_rate_hz_s'],
                    retained_bandwidth_hz=p['retained_bandwidth_hz'])
                f=r['inventory']['target']['rf_center_hz'];wavelength=299792458/f
                d['illustrative_differential_hz_bound']=.08/wavelength*8000/500000
                d['illustrative_120ms_geometric_phase_bound_deg']=360*.12*d['illustrative_differential_hz_bound']
                t=np.asarray(fit['time_s']);a=np.asarray(fit['curves_rad'][fit['selected']])
                d['fitted_residual_excursion_deg']=float(np.degrees(np.ptp(a)))
                d['median_absolute_spline_residual_frequency_hz']=float(np.median(abs(np.gradient(a,t)/(2*np.pi))))
                d['rf_hz']=f
            if m['state']=='replayed':
                d.update(matched_coherence=m['held']['tracked']['coherence'],
                         matched_wrong_time=m['held']['wrong_time']['coherence'],
                         matched_spline_rms_deg=m['curve_fits']['B_validation'][m['curve_fits']['selected']]['B_rms_deg'])
            details.append(d)
    save('summary.json',summary);save('per-dwell.json',details)
    with (ROOT/'per-dwell.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(dict.fromkeys(k for r in details for k in r)),lineterminator='\n')
        writer.writeheader();writer.writerows(details)
    save('validation.json',dict(production_parity_rows=parity,production_parity_count=len(parity),
        selected_dwell_count=len(details),unchanged_selection=True,
        physical_block_duration_ms=1.6384,matched_iq_hashes_verified=True,
        geometry_bound_assumptions=dict(mechanical_baseline_m=.08,relative_speed_upper_m_s=8000,range_lower_m=500000),
        geometry_bound_is_illustrative_not_measured=True))

    fig,axes=plt.subplots(2,3,figsize=(16,8),sharex=True,sharey=True,layout='constrained')
    for col,(entry,r,m) in enumerate(examples):
        for row,data in enumerate((dict(state=r['state'],curve_fits=r.get('curve_fits'),held=r.get('held_band_phase')),m)):
            ax=axes[row,col]
            if data['state']=='replayed':
                fit=data['curve_fits'];held=data['held']['rows'];rate=entry['sample_rate_hz']
                line(ax,np.asarray(fit['time_s'])*1000,fit['curves_rad'][fit['selected']],color='#0072B2',lw=1.6,label='A-selected curve')
                ax.scatter(np.array([p['center_sample']/rate*1000 for p in held]),
                           np.degrees(np.angle(np.exp(1j*np.array([p['training_band_phase_rad']+p['held_band_residual_phase_rad'] for p in held])))),
                           s=9,color='#D55E00',alpha=.65,label='Later B observations')
                rms=fit['B_validation'][fit['selected']]['B_rms_deg']
                ax.set_title(f"{rate/1e6:g} MS/s · visit {r['visit']} · B RMS {rms:.1f}°",fontsize=11)
            else:
                ax.text(.5,.5,'Abstained',transform=ax.transAxes,ha='center')
            ax.axvline(60,color='gray',ls=':');ax.grid(alpha=.2)
            ax.set(xlim=(0,120),ylim=(-185,185),yticks=[-180,-90,0,90,180])
            if row==1:ax.set_xlabel('Within-dwell time (ms)')
    axes[0,0].set_ylabel('Native 4096-sample blocks\nResidual phase (°)')
    axes[1,0].set_ylabel('Equal 1.6384 ms blocks\nResidual phase (°)')
    axes[0,0].legend(fontsize=8,loc='lower left')
    fig.suptitle('Phase tracking across saved sample rates · strongest paired-margin example per selected scan\nDifferent scans and signal conditions; each model has its own phase reference. No geometric phase or rate ranking implied.',fontsize=13)
    fig.savefig(ROOT/'phase-vs-time-by-rate.png',dpi=180);plt.close(fig)

    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for ax,rate in zip(axes,(2.5,10,15)):
        ds=[r for r in details if r['sample_rate_msps']==rate]
        for i,r in enumerate(ds):
            for x,key,color in [(i-.12,'native_spline_rms_deg','#0072B2'),(i+.12,'matched_spline_rms_deg','#D55E00')]:
                if key in r:
                    ax.scatter(x,r[key],c=color,s=45,marker='o' if r['native_supported' if 'native' in key else 'matched_supported'] else 'x')
                else:ax.text(x,133,'N/A',rotation=90,ha='center',fontsize=7)
        ax.set(title=f'{rate:g} MS/s · eight frozen dwells',xticks=range(len(ds)),xticklabels=[r['visit'] for r in ds],ylim=(0,150),xlabel='Visit index')
        ax.tick_params(axis='x',rotation=60);ax.grid(alpha=.2)
    axes[0].set_ylabel('Later B-band curve discrepancy (degrees RMS)')
    axes[0].scatter([],[],c='#0072B2',label='Native blocks')
    axes[0].scatter([],[],c='#D55E00',label='Equal-duration blocks')
    axes[0].scatter([],[],c='gray',marker='x',label='Fails phase support rule')
    axes[0].legend(fontsize=8)
    fig.suptitle('FFT-duration ablation on identical IQ · curve selected using A only\nMask, averaging and spectral resolution change together; lower discrepancy is not calibrated geometric accuracy.',fontsize=13)
    fig.savefig(ROOT/'block-duration-ablation.png',dpi=180);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    run()
