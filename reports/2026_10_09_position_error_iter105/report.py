"""Post-fit pilot reporting only; no objective evaluation or optimization."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

HERE=Path(__file__).resolve().parent
ARMS=('fitted-c','zero-c')
TERMINAL={'complete','failed','budget-exhausted','input-failed','not-run-baseline-failed'}


def load_phases(directory,protocol_sha256):
    """Missing candidate is report-only not-run when controller stopped on baseline."""
    phases={};hashes={}
    for phase in ('baseline','candidate'):
        path=directory/(phase+'.json')
        if not path.exists():
            if phase=='candidate' and phases.get('baseline',{}).get('status') in {'failed','budget-exhausted','input-failed'}:
                phases[phase]=dict(status='not-run-baseline-failed',protocol_sha256=protocol_sha256,
                                   reason='Controller stops after non-complete baseline; no candidate engine receipt exists',
                                   report_only=True)
                continue
            raise RuntimeError(f'{directory.name} {phase} not terminal; reference access withheld')
        value=json.loads(path.read_text())
        if value.get('status') not in TERMINAL-{'not-run-baseline-failed'}:
            raise RuntimeError(f'{directory.name} {phase} not terminal; reference access withheld')
        assert value['protocol_sha256']==protocol_sha256,'Fit belongs to another protocol'
        phases[phase]=value;hashes[phase]=hashlib.sha256(path.read_bytes()).hexdigest()
    return phases,hashes


def describe(operation,document):
    if not operation:return None
    fit=operation['fit'];prior=RegionalPrior(**document['configuration']['prior'])
    lat,lon=coordinates(prior,np.asarray(fit['vector'])[:2])
    lat,lon,rlat,rlon=map(math.radians,(lat,lon,document['reference_latitude_deg'],document['reference_longitude_deg']))
    h=math.sin((lat-rlat)/2)**2+math.cos(lat)*math.cos(rlat)*math.sin((lon-rlon)/2)**2
    return dict(error_km=2*6371.0088*math.asin(math.sqrt(min(1,max(0,h)))),
                **{k:fit.get(k) for k in ('objective','posterior_rms_hz','signal_windows','converged','stationarity','evaluations','stop_reason')},
                selection={k:operation.get(k) for k in ('region_source','basin','accepted_stage','start','calibration_penalty')})


def comparison(member,baseline,candidate,document):
    row=dict(label=member['label'],session_id=member['session_id'],source_version=member['source_version'],
             baseline_kind='fresh standard B7; not old hard60' if member['source_version']=='hard60' else 'standard B7 replay with archived parity check',
             baseline_status=baseline.get('status','missing'),candidate_status=candidate.get('status','missing'),
             baseline_failure=baseline.get('reason'),candidate_failure=candidate.get('reason'),fallback_available=candidate.get('fallback_available',False),
             trigger_count=len(candidate.get('inventory',{}).get('candidates',[])),
             trigger_failures=candidate.get('inventory',{}).get('failures',[]),
             stage_reasons=dict(baseline=baseline.get('reasons',[]),candidate=candidate.get('reasons',[])),arms={})
    for arm in ARMS:
        base=baseline.get('operational',{}).get(arm);new=candidate.get('operational',{}).get(arm)
        value=dict(baseline=describe(base,document),candidate=describe(new,document))
        if base and new:
            value['error_delta_km']=value['candidate']['error_km']-value['baseline']['error_km']
            value['objective_delta']=new['fit']['objective']-base['fit']['objective']
            value['regional_source_changed']=base.get('region_source')!=new.get('region_source')
        if member['source_version']=='B7' and base:
            stage=base.get('accepted_stage');old=document['diagnostics']['b7']['attempts'].get(stage,{}).get(arm)
            value['archived_parity']=dict(available=old is not None,vector_exact=old is not None and np.array_equal(old['vector'],base['fit']['vector']),objective_delta=None if old is None else base['fit']['objective']-old['objective'])
            value['archived_parity']['passed']=bool(old is not None and value['archived_parity']['vector_exact'] and value['archived_parity']['objective_delta']==0)
            if not value['archived_parity']['passed']:
                value['archived_parity']['limitation']='Archived B7 endpoint parity is unavailable or differs; do not claim exact replay parity'
        row['arms'][arm]=value
    recovered=[]
    for name,region in candidate.get('regions',{}).items():
        if not name.startswith('direct105:'):continue
        finals=[]
        for value in region.get('finals',[]):
            fit=value.get('fit') or {}
            finals.append(dict(arm=value.get('arm'),start=value.get('start'),qualified=bool(fit.get('converged')),stationarity=fit.get('stationarity'),stop_reason=fit.get('stop_reason'),reason=value.get('reason')))
        receipt=region.get('recovery',{});calibration=receipt.get('result') or {}
        recovered.append(dict(region=name,calibration_status=calibration.get('status'),reason=receipt.get('reason'),finals=finals))
    row['recovered_regions']=recovered
    return row


def aggregate(rows):
    output={}
    for arm in ARMS:
        complete=[r for r in rows if r['baseline_status']=='complete' and r['candidate_status']=='complete' and r['arms'][arm]['baseline'] and r['arms'][arm]['candidate']]
        item=dict(full_membership=len(rows),matched_complete=len(complete),failures_or_missing=len(rows)-len(complete),full_pilot_metrics_withheld=len(complete)!=len(rows))
        if len(complete)==len(rows):
            for phase in ('baseline','candidate'):
                values=np.asarray([r['arms'][arm][phase]['error_km'] for r in complete]);item[phase]=dict(mean_km=float(values.mean()),median_km=float(np.median(values)),p95_km=float(np.quantile(values,.95)),worst_km=float(values.max()))
            item['regressions']=[dict(label=r['label'],delta_km=r['arms'][arm]['error_delta_km']) for r in complete if r['arms'][arm]['error_delta_km']>1e-9]
        output[arm]=item
    return output


def collect_costs(directory):
    result=[]
    def visit(value,path):
        if isinstance(value,dict):
            metrics={k:value[k] for k in ('evaluations','feasible_evaluations','maximum_evaluations','elapsed_seconds','qualified','converged') if k in value}
            if metrics:result.append(dict(path=path,metrics=metrics))
            for k,v in value.items():visit(v,path+'/'+k)
        elif isinstance(value,list):
            for i,v in enumerate(value):visit(v,path+'/'+str(i))
    for path in sorted((directory/'stages').glob('*.json')):visit(json.loads(path.read_text()),path.name)
    return result


def main():
    snapshot=json.loads((HERE/'source-snapshot.json').read_text());rows=[];hashes={}
    protocol_sha256=hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
    # Check all fit statuses before any reference metadata is opened.
    loaded=[]
    for member in snapshot['members']:
        directory=HERE/'results'/member['label'];phases,phase_hashes=load_phases(directory,protocol_sha256)
        for phase,digest in phase_hashes.items():hashes[str((directory/(phase+'.json')).relative_to(HERE))]=digest
        loaded.append((member,directory,phases))
    for member,directory,phases in loaded:
        cls=B7Store if member['source_version']=='B7' else Hard60Store
        manifest=cls(Path('/srv/bulk/leo')).status(member['session_id']).manifest
        assert manifest.document_sha256==member['document_sha256'],'Source publication changed'
        row=comparison(member,phases['baseline'],phases['candidate'],manifest.document.model_dump(mode='json'))
        row['recorded_stage_costs']=collect_costs(directory)
        row['slice_claims']=[dict(path=str(p.relative_to(HERE)),receipt=json.loads(p.read_text())) for p in sorted((directory/'slices').glob('*.json'))]
        rows.append(row)
    result=dict(scope='Failure-selected five-member development pilot, not a population estimate; frequency-fit effects separate from position error',protocol_sha256=protocol_sha256,members=rows,aggregate=aggregate(rows),source_receipt_hashes=hashes,cost_scope='Persisted stage diagnostics; nested records can duplicate work and are not summed into total numerical evaluations')
    (HERE/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(2,2,figsize=(11,8))
    for column,arm in enumerate(ARMS):
        x=np.arange(len(rows));base=[r['arms'][arm]['baseline']['error_km'] if r['arms'][arm]['baseline'] else np.nan for r in rows];new=[r['arms'][arm]['candidate']['error_km'] if r['arms'][arm]['candidate'] else np.nan for r in rows]
        for level in (0,1):
            ax=axs[level,column]
            ax.bar(x-.18,base,.36,label='Matched standard B7');ax.bar(x+.18,new,.36,label='Generic recovery');ax.set_xticks(x,[r['label'].split('-')[-1] for r in rows]);ax.set_title(arm+(' — full range' if level==0 else ' — detail, 0–2.5 km'));ax.set_ylabel('Position error (km)');ax.legend(fontsize=8)
            ax.spines[['top','right']].set_visible(False)
            if level==1:
                ax.set_ylim(0,2.5)
                for i,value in enumerate(base):
                    if value>2.5:ax.annotate(f'{value:.1f} km ↑',(i-.18,2.35),ha='center',fontsize=8)
    fig.suptitle('Failure-selected development pilot; no population accuracy claim');fig.tight_layout();fig.savefig(HERE/'position_errors.png',dpi=160);plt.close(fig)
    lines=['# Generic calibration-recovery pilot','','All five failure-selected development members are accounted for. This pilot does not estimate population mean accuracy. Frequency fit and position error remain separate.','','![Matched position errors](position_errors.png)','','| Member | Arm | Baseline km | Candidate km | Delta km | Status |','|---|---|---:|---:|---:|---|']
    for row in rows:
        for arm in ARMS:
            value=row['arms'][arm];fmt=lambda v:'Unavailable' if v is None else f'{v:.6f}'
            lines.append(f"|{row['label']}|{arm}|{fmt(value['baseline']['error_km'] if value['baseline'] else None)}|{fmt(value['candidate']['error_km'] if value['candidate'] else None)}|{fmt(value.get('error_delta_km'))}|{row['baseline_status']} / {row['candidate_status']}|")
    lines.extend(['','## Pilot metrics','','These five members were selected for calibration failures, not position error. They are consumed development data. The known ac11 rescue is member051; its repetition under generic code is not independent validation.','','| Arm / phase | Mean km | Median km | p95 km | Worst km |','|---|---:|---:|---:|---:|'])
    for arm,stats in result['aggregate'].items():
        if stats['full_pilot_metrics_withheld']:
            lines.append(f'|{arm}: incomplete matched coverage|—|—|—|—|')
        else:
            for phase in ('baseline','candidate'):
                v=stats[phase];lines.append(f"|{arm} / {phase}|{v['mean_km']:.6f}|{v['median_km']:.6f}|{v['p95_km']:.6f}|{v['worst_km']:.6f}|")
    lines.extend(['','## Recovery convergence and failures','','Optimizer success alone is not qualification. Unqualified regional starts remain excluded by the unchanged independent gate. These are attempt failures even when a member completes with a valid ordinary winner.','','| Member | Recovery calibration | Qualified regional starts | Unqualified regional starts |','|---|---|---:|---:|'])
    for row in rows:
        regions=row['recovered_regions'];finals=[v for r in regions for v in r['finals']]
        lines.append(f"|{row['label'].split('-')[-1]}|{', '.join(str(r['calibration_status']) for r in regions)}|{sum(v['qualified'] for v in finals)} / {len(finals)}|{sum(not v['qualified'] for v in finals)}|")
    lines.extend(['','## Frequency fit, reported separately','','| Member | Arm | Baseline RMS Hz | Candidate RMS Hz |','|---|---|---:|---:|'])
    for row in rows:
        for arm,value in row['arms'].items():
            b=value['baseline'];c=value['candidate']
            if b and c:lines.append(f"|{row['label'].split('-')[-1]}|{arm}|{b['posterior_rms_hz']:.3f}|{c['posterior_rms_hz']:.3f}|")
    lines.extend(['','[comparison.json](comparison.json) contains per-arm signal support, convergence, fallbacks, regional selection, archived B7 parity, slice claims and recorded evaluation/polish diagnostics. Full-pilot aggregate metrics are withheld if any matched member fails.','','See [interpretation and next steps](INTERPRETATION.md), [independent runtime audit](RUNTIME_AUDIT.md), and [raw receipt restoration](RESULT_ARCHIVE.md).'])
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
