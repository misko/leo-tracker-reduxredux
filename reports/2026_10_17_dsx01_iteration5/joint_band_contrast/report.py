"""Render the sealed matched blocked-cold policy pilot without any fitting."""
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run import HERE,ATTEMPT,PROFILE,digest,read,save
from leo.analysis.regional_position_score import coordinates,zero_sum_basis
from leo.contracts.regional_position import RegionalPrior


def render():
    result=read(HERE/'results.json');rows=result['results'];lookup={(r['method'],r['arm']):r for r in rows}
    blocks=[]
    for arm in ['fitted-c','zero-c']:
        with np.load(HERE/f'evaluation-frozen-{arm}.npz') as f,np.load(HERE/f'evaluation-free-{arm}.npz') as p:
            indexes=np.floor(f['times_s']/20).astype(int)
            for block in np.unique(indexes[f['held_mask']]):
                use=f['held_mask']&(indexes==block)
                old=f['associated'][use];new=p['associated'][use]
                blocks.append(dict(arm=arm,start_s=int(block*20),end_s=int((block+1)*20),observations=int(use.sum()),
                    frozen_associated=int(old.sum()),free_associated=int(new.sum()),new=int((new&~old).sum()),lost=int((old&~new).sum()),
                    delta_frequency_nll=float((p['row_nll'][use]-f['row_nll'][use]).sum())))
    with (HERE/'held-blocks.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(blocks[0]));writer.writeheader();writer.writerows(blocks)
    window_rows=[]
    for r in rows:
        for w in r['windows']:
            for role in ['train','held','boundary']:
                window_rows.append(dict(method=r['method'],arm=r['arm'],region_id=w['region_id'],role=role,**w[role]))
    with (HERE/'window-comparison.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(window_rows[0]));writer.writeheader();writer.writerows(window_rows)
    timing=[]
    for r in rows:
        fit=read(HERE/f"fit-{r['method']}-{r['arm']}.json");v=np.array(fit['vector'])
        # The original orthonormal contrast basis is fixed by ordered bank size.
        k=len(v)-7;relative=zero_sum_basis(k)@v[8:]
        timing.append(dict(method=r['method'],arm=r['arm'],candidate_count=k,common_s=float(v[7]),
            relative_rms_s=float(np.sqrt(np.mean(relative**2))),relative_s=relative.tolist(),total_s=(v[7]+relative).tolist()))
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    for i,arm in enumerate(['fitted-c','zero-c']):
        data=[b for b in blocks if b['arm']==arm];axis=axes[0,i]
        axis.bar([b['start_s'] for b in data],[b['delta_frequency_nll'] for b in data],width=14,color=['#247a61' if b['delta_frequency_nll']<0 else '#b74c42' for b in data])
        axis.axhline(0,color='black',lw=.7);axis.set(title=f'{arm}: paired held blocks',xlabel='Block start (s)',ylabel='Free minus frozen NLL')
        axis=axes[1,i]
        for r in [t for t in timing if t['arm']==arm]:
            axis.hist(r['relative_s'],bins=np.arange(-50,54,4),histtype='step',lw=1.5,label=f"{r['method']} (n={r['candidate_count']}, RMS={r['relative_rms_s']:.2f}s)")
        axis.set(xlabel='Relative candidate timing (s)',ylabel='Candidates');axis.legend(fontsize=8)
    fig.savefig(HERE/'paired-blocks-and-timing.png',dpi=160);plt.close(fig)
    # Position is evaluation-only, after all fit/prediction freezes. Physical v[:2]
    # is east/north km, despite an incorrectly named raw-results field.
    terminal=read(ATTEMPT/'output/terminal.json');derivation=read(ATTEMPT/'derivation.json')
    prior=RegionalPrior(**terminal['provenance']['prior'])
    original_vector=np.asarray(read(ATTEMPT/'output/stages/shared-all-A-5.json')['result']['fit']['vector'])
    center=np.asarray(read(ATTEMPT/'output/stages/shape-all.json')['result']['winner']['theta'][:2])
    station_path=HERE.parents[2]/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    reference=read(station_path);source=read(ATTEMPT/'training-input.json')['source']
    assert source['radio_id']==reference['radio_serial']
    assert reference['valid_from_utc_ns']<=derivation['origin_utc_ns']<reference['valid_until_utc_ns']
    positions=[]
    for r in rows:
        fit=read(HERE/f"fit-{r['method']}-{r['arm']}.json");v=np.asarray(fit['vector'])
        latitude,longitude=coordinates(prior,v[:2]);lat,lon=np.radians([latitude,longitude]);a,b=np.radians([reference['latitude_deg'],reference['longitude_deg']])
        h=np.sin((a-lat)/2)**2+np.cos(lat)*np.cos(a)*np.sin((b-lon)/2)**2
        distance=float(2*6371.0088*np.arcsin(np.sqrt(h)))
        local_distance=float(np.linalg.norm(v[:2]-center))
        positions.append(dict(method=r['method'],arm=r['arm'],east_north_km=v[:2].tolist(),latitude_deg=latitude,longitude_deg=longitude,
            configured_reference_distance_km=distance,movement_from_terminal_km=float(np.linalg.norm(v[:2]-original_vector[:2])),
            old_production_local_center_km=center.tolist(),distance_from_old_production_center_km=local_distance,
            within_old_production25km_disk=bool(local_distance<=25+1e-9),within_broad250km_disk=bool(np.linalg.norm(v[:2])<=250+1e-9)))
    save(HERE/'position-diagnostic.json',dict(positions=positions,reference_sha256=digest(station_path),
        reference_evidence=reference['position_evidence'],reference_usage='Only after all endpoint/prediction freezes; no seeding or selection',
        original_production_center_authority=dict(path=str(ATTEMPT/'output/stages/shape-all.json'),sha256=digest(ATTEMPT/'output/stages/shape-all.json'),
            semantics='A-5 index5 uses shape-all winner theta[:2] as center; bounded_shared_fit default local_radius_km25'),
        raw_results_field_correction='position_vector_deg in raw results.json is erroneously named; its two numbers are east/north kilometers. This diagnostic decodes the actual v[:2] using public coordinates().'))
    fitted=lookup['free','fitted-c'];base=lookup['frozen','fitted-c'];paired=[b for b in blocks if b['arm']=='fitted-c']
    best=min(paired,key=lambda b:b['delta_frequency_nll']);total=sum(b['delta_frequency_nll'] for b in paired)
    summary=dict(results=rows,held_blocks=blocks,timing=timing,positions=positions,evaluation_denominators=result['evaluation_denominators'],
        fitted_primary=dict(net_held=fitted['held']['associated']-base['held']['associated'],
            delta_held_nll=total,improved_blocks=sum(b['delta_frequency_nll']<0 for b in paired),held_blocks=len(paired),
            largest_gain_block=best,other_blocks_delta_nll=total-best['delta_frequency_nll'],
            requested_held_before=sum(w['held']['associated'] for w in base['windows']),requested_held_after=sum(w['held']['associated'] for w in fitted['windows']),
            major_held_windows_before=sum(w['held']['associated']>=.8*w['held']['observations'] for w in base['windows']),
            major_held_windows_after=sum(w['held']['associated']>=.8*w['held']['observations'] for w in fitted['windows'])),
        verdict='Small positive single-source blocked-interpolation policy result; held gains and losses and block concentration retained; no all-source/new-position/identity-truth/whole-pipelinec0 conclusion.')
    save(HERE/'summary.json',summary)
    table=['| Policy | c arm | Train / 2073 | Held / 1909 | Requested held / 80 | Held NLL | Calls | KKT |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        table.append(f"| {r['method']} | {r['arm']} | {r['train']['associated']} | {r['held']['associated']} | {sum(w['held']['associated'] for w in r['windows'])} | {r['held']['frequency_nll']:.2f} | {r['diagnostics']['evaluations']} | {r['diagnostics']['stationarity']:.3g} |")
    lines=['# Joint constant-band contrast: blocked interpolation pilot','',
        f"The fitted-c TRAIN-profile plus joint-band policy improves held coverage from {base['held']['associated']} to {fitted['held']['associated']}/1909 and requested held coverage from 68 to 70/80 versus matched frozen-band continuation. Held NLL changes by {total:.2f}. This is a single previously selected source, not completion of the 15-window goal.",'',
        *table,'',
        f"Fitted-c held gains are {fitted['held']['new_vs_frozen']} and losses {fitted['held']['lost_vs_frozen']}, leaving {fitted['held']['retained_vs_frozen']} retained. On that intersection, frequency RMS changes {fitted['held']['intersection_frozen_rms_hz']:.2f} to {fitted['held']['intersection_current_rms_hz']:.2f} Hz. Overall associated RMS changes {base['held']['associated_rms_hz']:.2f} to {fitted['held']['associated_rms_hz']:.2f} Hz; the selected sets differ.",'',
        f"Held NLL improves in {sum(b['delta_frequency_nll']<0 for b in paired)}/{len(paired)} blocks. The strongest block ({best['start_s']}–{best['end_s']} s) contributes {best['delta_frequency_nll']:.2f}; the other blocks sum to {total-best['delta_frequency_nll']:.2f}. The preceding fixed-state profile gain was concentrated in the 260–280 s block, so this follow-up also reports every held block rather than treating an aggregate gain as broad transfer.",'',
        'The three requested held windows change 007:21→21/26 (one gain, one loss), 008:21→24/28 (three gains), and 009:26→25/26 (one loss). Thus windows at ≥80% change 2→3/3, with net requested gain two. These 80 points occupy only two held time blocks. All 693 requested points remain accounted as 58 train,80 held,0 boundary and555 other-source points untested. All20084 context points remain2073 train,1909 held,6 boundary and16096 other-source points untested. No untested point is counted as recovered.','',
        'Both arms use the original fixed TRAIN-discovered bank of45 candidates and native0–300s learned clock. Membership uses whole probes in deterministic alternating20s counter blocks, excluding straddlers; the clock interpolates across gaps. No held CFO, gate or score enters selection, discovery, seeds or calibration. All four endpoints and then their metadata-only predictions were frozen before held scoring. The classifier remains best satellite posterior > clutter at the original125Hz width. Labels are model associations, not confirmed emitter identities.','',
        'The free model retains all physical, timing, clock and q parameters, original q budget and all priors. Only receiver high-band constants become free, bounded by the original absolute alias limits with5000Hz scales. The frozen absolute contrast prior is replaced by the variable absolute50000Hz prior exactly once. A research subclass preserves exact singleton original objective and all existing gradients at the original contrasts, including the q/visibility normalizer terms. Seven component tests pass; actual training objective/gradient nesting, exact correction transport, CFO-invariant predictions and all four strict endpoints are independently replayed in verification.json.','',
        'Each policy has1000 objective/density calls and120s maximum. The free policy charges the sealed159-call TRAIN-only profile plus2 real seed qualifications, leaving839 calls for joint refit; fittedc uses342 andc0 uses438, totaling503/599. Original incumbents remain eligible. Frozen control endpoints are exactly reused after all pinned source files, identical terminal seeds, all-2s wrapper semantics, bank/mask/prior and endpoint objectives/gradients are qualified:287/431 calls. Reuse and independent replay costs are separate from optimization in results.json and verification.json. This compares profile+joint policy with frozen continuation, not a pure causal effect of adding two parameters.','',
        'Both continuations use common.refit’s broad regional disk. The extra25km disk from original production is not imposed. This is explicitly a matched research continuation domain, not an unchanged production-policy comparison. Original TRAIN discovery used fittedc; c0 sets only physicalvector[6]=0 at the common terminal seed and fixes it during continuation. It is conditional downstream sensitivity, not whole-pipelinec0. Better frequency fit alone establishes no location-accuracy improvement.','',
        'Position diagnostics use the matching configured reference only after prediction freeze; it is operator-supplied and survey uncertainty is unknown. The physical vector begins with east/north kilometers, not latitude/longitude; the raw results field position_vector_deg was misnamed. position-diagnostic.json decodes public coordinates and records each endpoint’s distance from the original shape-all production center and whether it lies within the original25km disk.','',
        '| Policy | c arm | Configured distance km | Movement from terminal km | Old center distance km | Within old25km |',
        '|---|---|---:|---:|---:|---|',
        *[f"| {p['method']} | {p['arm']} | {p['configured_reference_distance_km']:.3f} | {p['movement_from_terminal_km']:.3f} | {p['distance_from_old_production_center_km']:.3f} | {p['within_old_production25km_disk']} |" for p in positions],'',
        'Donor contrasts were frozen before final geometry/timing/clock/q optimization. A shifted coupled optimum can motivate joint constants. The conditional-density normalizer is not itself evidence of an old frequency-gradient bug: at identical predictions, hard visibility and uniformq, legacy and shared frequency gradients agree. This pilot does not identify a unique cause. No drift term, expanded bank, special satellite/window seed or station-coordinate initialization was added.','',
        'Fitted-c absolute contrasts (Hz): frozen[-15031.27,34766.82], free[-15379.91,37631.22], updates[-348.64,+2864.40]. Conditionalc0 free updates[-1432.73,+2387.49]. All4 endpoints pass the unchanged≤0.001 KKT threshold; c0 free is close at0.000969. No relaxed tolerance or extra cleanup run was used.','',
        '![Paired held blocks and same-count timing histograms](paired-blocks-and-timing.png)','',
        'Files: protocol.json binds prefit policy/hashes; control-reuse-qualification.json and qualification-*.json bind exact seeds; endpoint-freeze.json and prediction-freeze.json establish evaluation order; fit-*.json/predictions-*.npz/evaluation-*.npz retain endpoints and measurements; held-blocks.csv and window-comparison.csv retain losses and denominators. No additional fits were launched for this report.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    files=[dict(path=str(p.relative_to(HERE)),sha256=digest(p)) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
    save(HERE/'manifest.json',dict(files=files,sealed=True,scope='Single matched blocked source, four endpoints; two exactly reused controls and two new bounded joint fits'))
    print(json.dumps(summary['fitted_primary']))


if __name__=='__main__':render()
