"""Saved-result RF report and separate final evaluation; never runs inference."""
import argparse
import csv
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare import HERE,load,sha,write


def verify(path):
    for name,digest in load(path)['files'].items():
        assert sha(name)==digest,'sealed artifact changed '+name


def csv_write(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader();writer.writerows(rows)


def rf():
    verify(HERE/'RF_seal.json')
    out=HERE/'rf_report';out.mkdir(exist_ok=False)
    owners=load(HERE/'nomination_manifest.json')['owners'];corrections=load(HERE/'corrections.json');rows=[]
    fig,axes=plt.subplots(len(owners),2,figsize=(12,2.3*len(owners)),layout='constrained')
    for owner,axs in zip(owners,axes,strict=True):
        rr=sorted((r for r in corrections['rows'] if r['complete_owner']==owner['owner']),key=lambda r:(r['time_s'],r['native_observation_id']))
        t=np.array([r['time_s'] for r in rr]);a=np.array([r['original_cfo_hz'] for r in rr]);b=np.array([r['corrected_cfo_hz'] for r in rr]);delta=b-a
        axis=(t-np.mean(t))/max(1,np.ptp(t));fit_a=np.polynomial.polynomial.polyfit(axis,a,2);fit_b=np.polynomial.polynomial.polyfit(axis,b,2)
        rms_a=float(np.sqrt(np.mean((a-np.polynomial.polynomial.polyval(axis,fit_a))**2)))
        rms_b=float(np.sqrt(np.mean((b-np.polynomial.polynomial.polyval(axis,fit_b))**2)))
        row=dict(case=owner['case'],owner=owner['owner'],receiver=owner['receiver'],channel=owner['channel'],points=len(rr),
            span_s=owner['span_s'],parity_complete=sum(r['payload_and_parity_complete'] for r in rr),frequency_qualified=sum(r['numerical_frequency_qualified'] for r in rr),
            correction_mean_hz=float(delta.mean()),correction_rms_hz=float(np.sqrt(np.mean(delta**2))),correction_min_hz=float(delta.min()),correction_max_hz=float(delta.max()),
            descriptive_degree2_rms_original_hz=rms_a,descriptive_degree2_rms_refined_hz=rms_b)
        rows.append(row)
        label=f"{owner['case']} RX{owner['receiver']} CH{owner['channel']} {owner['owner'].split('-T')[1].split('-')[0]} ({len(rr)} points)"
        axs[0].plot(t,a/1000,'.-',ms=3,lw=.7,label='Original');axs[0].plot(t,b/1000,'.',ms=2,label='Refined');axs[0].set_ylabel('Native CFO (kHz)');axs[0].set_title(label)
        axs[1].plot(t,delta,'.-',ms=3,lw=.7);axs[1].axhline(0,color='.6',lw=.7);axs[1].set_ylabel('Correction (Hz)');axs[1].set_title(f"RMS {row['correction_rms_hz']:.1f} Hz; fixed quadratic scatter {rms_a:.1f} → {rms_b:.1f} Hz")
        for ax in axs:
            ax.set_xlabel('Original scan time (s)');ax.grid(alpha=.2)
    axes[0,0].legend();fig.suptitle('Complete frozen owners; missing DS24-0011 RX2 CH7 retained separately')
    fig.savefig(out/'complete_owner_corrections.png',dpi=150);plt.close(fig)
    windows=[]
    for f in sorted(HERE.glob('*_worker*.jsonl')):
        for line in f.read_text().splitlines():
            import json
            try:
                value=json.loads(line)
            except json.JSONDecodeError:
                continue
            if value.get('kind')=='window':
                windows.append(value)
    fields={};candidate_count=0
    for window in windows:
        for parity in window.get('candidate_parity',{}).values():
            candidate_count+=sum(c['field']=='candidate_rank' for c in parity['checks'])
            for check in parity['checks']:
                if 'error' in check and check['error'] is not None:
                    fields[check['field']]=max(fields.get(check['field'],0),check['error'])
    summary=dict(owners=rows,total_native_points=len(corrections['rows']),coverage_complete=corrections['coverage_complete'],
        all_frequency_qualified=corrections['all_frequency_qualified'],expected_owner_cells=8,available_owner_cells=7,
        missing_owner_cells=load(HERE/'nomination_manifest.json')['unavailable_owner_cells'],
        paired_physical_windows=len(windows),archived_complete_candidate_rows_compared=candidate_count,max_parity_error=fields,
        cumulative_worker_seconds=sum(load(HERE/(s+'_summary.json'))['cumulative_worker_seconds'] for s in ('initial','complete')),
        GPS_used=False,degree2_is_descriptive_not_physical_truth=True)
    write(out/'summary.json',summary);csv_write(out/'owner_summary.csv',rows)
    write(out/'RF_seal.json',dict(files={str(p):sha(p) for p in [HERE/'RF_seal.json',Path(__file__),out/'summary.json',out/'owner_summary.csv',out/'complete_owner_corrections.png']},GPS_used=False))
    print(summary)


def distance(a,b):
    la,lo,lb,lp=map(math.radians,(*a,*b));h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lp-lo)/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def latlon(point):
    return 37.906+point[1]/111.,-122.545+point[0]/(111.32*math.cos(math.radians(37.906)))


def geography(reference):
    verify(HERE/'RF_seal.json');verify(HERE/'position/RF_seal.json');verify(HERE/'rf_report/RF_seal.json')
    out=HERE/'geographic';out.mkdir(exist_ok=False)
    execution=load(HERE/'position/execution.json');rows=[row for case in execution['results'] for row in case['rows']];paired=[]
    for row in rows:
        row['error_km']=distance(latlon(row['endpoint_east_north_km']),reference) if row['status']=='complete' else None
    for case in ('DS24-0010','DS24-0011'):
        for kind in ('ordinary_VI','fixed_original_full_precision_packet'):
            case_rows=[r for r in rows if r['case']==case and r['kind']==kind]
            control_ok=all(r['status']=='complete' and (r['method']!='original' or kind!='ordinary_VI' or
                (r['original_endpoint_difference_km']<=.001 and abs(r['original_objective_difference'])<=1e-3)) for r in case_rows)
            pair_ok=control_ok and all(r['single_arm_valid'] and r['Gamma_converged'] and r['final_phase_change_s']<=.01 and
                r['maximum_unclipped_phase_s']<=15.000001 and r['all_original_accepted_IDs_preserved'] for r in case_rows if r['method']=='refined')
            for arm in ('c0','fitted_c'):
                bymethod={r['method']:r for r in case_rows if r['arm']==arm};a=bymethod.get('original');b=bymethod.get('refined')
                if not a or not b:
                    paired.append(dict(case=case,kind=kind,arm=arm,status='unavailable'));continue
                paired.append(dict(case=case,kind=kind,arm=arm,status='complete' if a['status']==b['status']=='complete' else 'failed',
                    original_error_km=a['error_km'],refined_error_km=b['error_km'],gain_m=1000*(a['error_km']-b['error_km']) if a['error_km'] is not None and b['error_km'] is not None else None,
                    objective_difference=b.get('objective',0)-a.get('objective',0),conditional_RMS_difference_hz=b.get('conditional_RMS_hz',0)-a.get('conditional_RMS_hz',0),
                    endpoint_movement_m=float(np.linalg.norm(np.asarray(b['endpoint_east_north_km'])-a['endpoint_east_north_km'])*1000) if a['status']==b['status']=='complete' else None,
                    postfit_IDs_lost=b.get('postfit_IDs_lost'),paired_research_qualified=bool(pair_ok),
                    regional_end_to_end_gain_established=False))
    write(out/'summary.json',dict(rows=rows,paired=paired,reference_latlon=reference,inference_RF_seal_sha256=sha(HERE/'position/RF_seal.json'),
        evaluation_only_GPS=True,expected_owner_cells=8,available_owner_cells=7,independent_validation=False))
    csv_write(out/'paired.csv',paired)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained',sharey=True)
    for ax,kind in zip(axes,('ordinary_VI','fixed_original_full_precision_packet'),strict=True):
        pp=[p for p in paired if p['kind']==kind]
        for i,p in enumerate(pp):
            if p['status']!='complete':
                continue
            ax.bar(i-.17,p['original_error_km'],.32,color='.6',label='Original' if i==0 else None)
            ax.bar(i+.17,p['refined_error_km'],.32,color='#16778a',label='Refined' if i==0 else None)
            ax.text(i,max(p['original_error_km'],p['refined_error_km'])+.03,f"{p['gain_m']:+.0f} m"+(' *' if not p['paired_research_qualified'] else ''),ha='center',fontsize=9)
        ax.set_xticks(range(len(pp)),[p['case'][-4:]+'\n'+p['arm'] for p in pp]);ax.set_title(kind.replace('_',' '));ax.set_ylabel('Final evaluation position error (km)');ax.legend();ax.grid(axis='y',alpha=.2)
    fig.suptitle('Fixed assignments, cold zero initialization; * paired gates fail')
    fig.savefig(out/'matched_position_errors.png',dpi=180);plt.close(fig)
    write(out/'seal.json',dict(files={str(p):sha(p) for p in out.iterdir() if p.is_file()}))
    print(paired)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('rf','geography'));parser.add_argument('--reference-latlon',nargs=2,type=float)
    args=parser.parse_args()
    if args.action=='rf':
        rf()
    else:
        if args.reference_latlon is None:
            parser.error('final evaluation requires explicit reference')
        geography(args.reference_latlon)
