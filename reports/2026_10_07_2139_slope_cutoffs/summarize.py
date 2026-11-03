"""Independent repricing, matched-trial audit and readable cutoff comparisons."""

import csv
import json
from pathlib import Path
import sys

import numpy as np
import experiment as e
import compare as prior_audit

HERE=e.HERE
OPTIONS=['control','window60','window30','window10']
LABELS=['Unrestricted','±60','±30','±10']


def trial_key(r):
    return r['basin'],r['arm'],r['stage'],r['seed_label']


def csv_write(name,rows):
    with (HERE/name).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def flatten(r,scope):
    return dict(option=r['option'],scope=scope,arm=r['arm'],basin=r['basin'],origin=r['origin'],
                position_error_km=r['horizontal_error_m']/1000,
                pair_median_hz=r['pair_clock']['median_absolute_residual_hz'],
                pair_p90_hz=r['pair_clock']['p90_absolute_residual_hz'],
                pair_residual_slope_hz_s=r['pair_clock']['robust_residual_slope_hz_s'],
                posterior_rms_hz=r['posterior_rms_hz'],data_nll=r['data_nll'],timing_penalty=r['timing_penalty'],
                selection_score=r['selection_score'],converged=r['converged'],stationarity=r['stationarity'],
                boundary=r['boundary'],slope_bound_hit=bool(r['slope_active_bounds']),
                rx0_additional_hz_s=r['vector'][3],rx1_additional_hz_s=r['vector'][5],
                rx0_total_linear_hz_s=r['total_linear_slopes_hz_s'][0],rx1_total_linear_hz_s=r['total_linear_slopes_hz_s'][1],
                c_hz_per_ghz=r['vector'][6])


def main():
    case,anchor,pairs,objects=e.freeze_inputs()
    results={o:e.read(HERE/o/'results.json') for o in OPTIONS}
    assert all(r['status']=='complete' for r in results.values())
    for o,d in results.items():
        assert d['source_hashes']==results['control']['source_hashes']
        assert d['relative_sigma_s']==1 and d['seconds_per_fit']==20 and d['maximum_iterations']==600
        assert len(d['runs'])==24 and len(d['seeds'])==24
        assert all(r['status']=='complete' for r in d['runs'])
    for path,hash_value in results['control']['source_hashes'].items():
        assert e.common.digest(Path(path).read_bytes())==hash_value
    seeds={o:{trial_key(r):r for r in d['seeds']} for o,d in results.items()}
    assert all(set(s)==set(seeds['control']) for s in seeds.values())
    for identity,base in seeds['control'].items():
        for o in OPTIONS:
            row=seeds[o][identity];v=np.asarray(row['vector']);before=np.asarray(row['unprojected_vector'])
            assert row['seed_sha256']==e.common.vector_digest(v)
            if row['stage']=='primary':assert row['shared_seed_sha256']==base['shared_seed_sha256']
            expected=e.project(before,e.common.OPTIONS[o],objects[row['basin']].prior.radius_km,case['basins'][row['basin']]['center_km'])
            np.testing.assert_array_equal(v,expected)
            if row['arm']=='zero-c': assert v[6]==0
    audits=[];rows=[];region_rows=[]
    for option,d in results.items():
        # Verify continuation is seeded from its own primary pool (incl own incumbents).
        for seed in d['seeds']:
            if seed['stage']!='continuation':continue
            pool=[r for r in d['candidates'] if r.get('stage')!='continuation']
            expected=e.choose(pool,seed['arm'],seed['basin'])
            assert e.common.vector_digest(expected['vector'])==seed['shared_seed_sha256']
        for row in d['selections']+d['regional_selections']+d['by_start']:
            v=np.asarray(row['vector']);obj=objects[row['basin']];region=case['basins'][row['basin']]
            value,g,t=obj.evaluate(v)
            stationarity=prior_audit.kkt(v,g,obj,region,row['arm'],e.common.OPTIONS[option])
            np.testing.assert_allclose(value,row['objective'],atol=1e-6,rtol=0)
            np.testing.assert_allclose(t.nll,row['data_nll'],atol=1e-6,rtol=0)
            np.testing.assert_allclose(stationarity,row['stationarity'],atol=1e-5,rtol=0)
            actual=e.pair_metrics(obj,v,pairs)
            for k,val in row['pair_clock'].items():np.testing.assert_allclose(actual[k],val,atol=1e-6,rtol=0)
            ref=case['evaluation_reference'];a,b=np.radians([ref['latitude_deg'],ref['longitude_deg']])
            lat,lon=np.radians(e.common.coordinates(obj.prior,v[:2]));h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
            error=2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1)))
            np.testing.assert_allclose(error,row['horizontal_error_m'],atol=1e-5,rtol=0)
            audits.append(dict(option=option,basin=row['basin'],arm=row['arm'],origin=row['origin'],stationarity=stationarity))
        for r in d['selections']:
            assert r==e.choose(d['candidates'],r['arm'])
            rows.append(flatten(r,'overall-three-regions'))
        for r in d['regional_selections']:
            assert r==e.choose(d['candidates'],r['arm'],r['basin'])
            region_rows.append(flatten(r,'region'))
            if r['basin']==anchor['basin']:rows.append(flatten(r,'anchor-region-best'))
        for r in d['by_start']:
            pool=[x for x in d['candidates'] if x.get('stage')=='primary' and x.get('seed_label')==r['seed_label']]
            assert r==e.choose(pool,r['arm'],anchor['basin'])
            rows.append(flatten(r,'start:'+r['seed_label']))
    csv_write('comparison.csv',rows);csv_write('regional_comparison.csv',region_rows)
    lookup={(r['option'],r['scope'],r['arm']):r for r in rows}
    nesting=[]
    for arm in e.common.ARMS:
        for scope in ['overall-three-regions','anchor-region-best']:
            for i,wider in enumerate(OPTIONS[:-1]):
                for narrower in OPTIONS[i+1:]:
                    gap=lookup[wider,scope,arm]['selection_score']-lookup[narrower,scope,arm]['selection_score']
                    if gap>1e-5:nesting.append(dict(wider=wider,narrower=narrower,scope=scope,arm=arm,gap=gap))
    summary=dict(capture=case['session_id'],runs=96,independent_audits=audits,width_nesting_gaps=nesting,
                 c_nesting_gaps={o:d['nested_c_gaps'] for o,d in results.items()},
                 elapsed_s={o:d['elapsed_s'] for o,d in results.items()},
                 total_fit_seconds=sum(d['fit_elapsed_s'] for d in results.values()),
                 selected=rows,region_selected=region_rows)
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['Hard additional slope cutoffs: corrected 2139 test',
           'Capture Oct 6 14:39 PDT, scan-fw-e3bebc228093a125; V16 relative timing sigma=1s.',
           'Both c arms, three fixed geographic regions, including the previously omitted clock-anchor region.',
           'Limits apply to additional slopes after calibration, not total instantaneous drift.',
           'Comparison format: error km / median absolute pair residual Hz / convergence', '']
    for arm in ['zero-c','fitted-c']:
        lines += [arm,'scope | unrestricted | +/-60 | +/-30 | +/-10']
        for scope in ['start:pre-repair-own-state','start:anchor-rx0','start:anchor-rx1','anchor-region-best','overall-three-regions']:
            entries=[lookup[o,scope,arm] for o in OPTIONS]
            lines.append(scope+' | '+' | '.join(f'{r["position_error_km"]:.3f} / {r["pair_median_hz"]:.1f} / {r["converged"]}' for r in entries))
        lines.append('')
    lines += ['Per-arm historical seeds are kept fixed across widths; no solution is copied across c arms.',
              'Region-specific retained incumbents are identical across options where feasible.',
              'Overall score selection is distinct from best reference-position accuracy.',
              f'Completed 96 fits; audited {len(audits)} selection entries including repeated overall/regional rows.',
              f'Width nesting gaps above 1e-5: {len(nesting)}. These expose finite-search differences.',
              'See comparison.csv for separate frequency NLL, timing penalty, RMS, slopes, bound and convergence flags.',
              'Single retrospective capture and three frozen regions; not full global search or deployment validation.']
    (HERE/'report.txt').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
    plot(lookup)


def plot(lookup):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    fig.subplots_adjust(left=.08,right=.98,bottom=.22,top=.83,hspace=.32,wspace=.22)
    fig.suptitle('14:39 capture: what hard slope limits change',fontsize=19,weight='bold',y=.98)
    fig.text(.5,.93,'V16 · zero-c · timing σ = 1 s · same observations and budgets\nPosition and receiver-pair consistency are separate outcomes',ha='center',va='top',fontsize=11)
    scopes=[('start:pre-repair-own-state','Bad pre-repair start','#d77324'),
            ('start:anchor-rx0','RX0-preserving pair-clock start','#267bc1'),
            ('overall-three-regions','Best score across all three regions','#27936b')]
    metrics=[('position_error_km','Position error (km)'),('pair_median_hz','Median receiver-pair mismatch (Hz)'),
             ('rx0_additional_hz_s','RX0 additional slope (Hz/s)'),('rx1_additional_hz_s','RX1 additional slope (Hz/s)')]
    for ax,(metric,label) in zip(axes.flat,metrics):
        for scope,name,color in scopes:
            group=[lookup[o,scope,'zero-c'] for o in OPTIONS];vals=[r[metric] for r in group]
            ax.plot(range(4),vals,'o-',color=color,lw=1.5,ms=5,label=name)
            bad=[i for i,r in enumerate(group) if not r['converged']]
            ax.scatter(bad,[vals[i] for i in bad],marker='x',color='black',s=65,zorder=5)
        ax.set_ylabel(label);ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
        if metric=='pair_median_hz':
            ax.set_yscale('log');ax.set_ylim(40,9000)
            ticks=[50,100,300,1000,3000]
            ax.set_yticks(ticks,[str(t) for t in ticks])
        elif metric=='rx0_additional_hz_s':
            ax.set_ylim(-5,.5);ax.set_yticks([-5,-4,-3,-2,-1,0]);ax.axhline(0,color='gray',lw=.6)
        elif metric=='rx1_additional_hz_s':
            ax.set_yscale('symlog',linthresh=5);ax.set_ylim(-150,2)
            ticks=[-100,-60,-30,-10,-5,0]
            ax.set_yticks(ticks,[str(t) for t in ticks]);ax.axhline(0,color='gray',lw=.6)
    for ax in axes[-1]:ax.set_xticks(range(4),LABELS);ax.set_xlabel('Hard cutoff on each receiver, Hz/s')
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.065),ncol=1,frameon=False)
    fig.text(.5,.025,'× = nonstationary. All slopes are additional to frozen calibration. Lines connect experimental options.',ha='center',fontsize=9)
    fig.savefig(HERE/'zero_c_comparison.png',dpi=180,facecolor='white')
    fig.savefig(HERE/'zero_c_comparison.svg',facecolor='white');plt.close(fig)


if __name__=='__main__':main()
