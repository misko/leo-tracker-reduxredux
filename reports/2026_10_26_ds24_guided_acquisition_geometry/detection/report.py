"""Figures and transparent trial-level reporting; no inference rerun."""
import csv
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from bounds import binomial_upper,independent_mean_upper

HERE=Path(__file__).resolve().parent
def load(name):return json.loads((HERE/name).read_text())
recorded=load('recorded.json');active=load('active_null.json');noise=load('noise_null.json')
labels=['zero_zero','weak_weak','strong_weak','strong_zero']


def summarize(rows):
    return dict(n=len(rows),active_donors=sum(r['guided']['active_donors']>0 for r in rows),
        correct_primary_donor=sum(bool(r['donor_truth_evaluation']and r['donor_truth_evaluation'][0]['matched'])for r in rows),
        wrong_primary_donor=sum(bool(r['donor_truth_evaluation']and not r['donor_truth_evaluation'][0]['matched'])for r in rows),
        no_donor=sum(not r['donor_truth_evaluation']for r in rows),
        blind_recovered=sum(r['blind_recovered']for r in rows),
        blind_any_accepted=sum(r['blind_any_accepted']for r in rows),
        primary_recovered=sum(r['guided']['primary_recovered']for r in rows),
        all_proposal_recovered=sum(r['guided']['any_recovered']for r in rows),
        primary_accepted=sum(r['guided']['primary_accepted']for r in rows),
        all_proposal_accepted=sum(r['guided']['any_accepted']for r in rows),
        oracle_accepted=sum(r['oracle_accepted']for r in rows),
        oracle_finalized_CFO_within100=sum(abs(r['oracle']['tracking_cfo_hz']-213456.75)<=100 for r in rows))


groups={label:[dict(request_id=s['request_id'],**r)for s in recorded['rows']if label in s['scenarios']
    for r in s['scenarios'][label]['outcomes']]for label in labels}
summary=dict(recorded={label:summarize(rows)for label,rows in groups.items()},
    failures=[dict(request_id=s['request_id'],error=s.get('error'))for s in recorded['rows']if s['status']!='complete'],
    seconds=dict(recorded=recorded['seconds'],active_null=active['seconds'],noise_null=noise['seconds']),
    nulls={},per_RX_channel={})


def null_summary(rows):
    n=len(rows);out=dict(n=n,active_donor_trials=sum(r['guided']['active_donors']>0 for r in rows),methods={})
    for key,read in [('blind',lambda r:r['blind_any_accepted']),('primary',lambda r:r['guided']['primary_accepted']),
                     ('all_proposals',lambda r:r['guided']['any_accepted'])]:
        k=sum(read(r)for r in rows)
        out['methods'][key]=dict(events=k,empirical_fraction=k/n,
            conservative_independent_average_FAR_95_upper=independent_mean_upper(k,n))
    return out


for name,data in [('active',active),('noise',noise)]:
    group=null_summary(data['rows']);group['strata']={}
    for edge in ['lower','upper']:
        for rx in [1,2]:
            rr=[r for r in data['rows']if r['edge']==edge and r['receiver']==rx]
            stratum=null_summary(rr)
            for value in stratum['methods'].values():
                value['exact_binomial_FAR_95_upper']=binomial_upper(value['events'],len(rr))
            group['strata'][f'{edge}_RX{rx}']=stratum
    group['paired_outcomes']={f'blind{int(b)}_primary{int(g)}':sum(r['blind_any_accepted']==b and r['guided']['primary_accepted']==g for r in data['rows'])
        for b in [False,True]for g in [False,True]}
    summary['nulls'][name]=group
for ch in [1,4,7,8]:
    for rx in [1,2]:summary['per_RX_channel'][f'CH{ch}_RX{rx}']={label:summarize([r for r in groups[label]if r['channel']==ch and r['receiver']==rx])for label in labels}

strong=groups['strong_weak']
guided_errors=[r['guided']['primary']['truth']['CFO_error_hz']for r in strong if r['guided']['primary']]
correct=[r for r in strong if r['donor_truth_evaluation']and r['donor_truth_evaluation'][0]['matched']]
summary['frequency']=dict(correct_donors=len(correct),correct_donor_guided_bin_hops=sum(abs(r['guided']['primary']['score']['residual_cfo_hz'])>100 for r in correct),
    bin_spacing_hz=1/(512*4.4e-6),oracle_gatepass=len([r for r in strong if r['oracle_accepted']]),
    oracle_final_CFO_over100=sum(abs(r['oracle']['tracking_cfo_hz']-213456.75)>100 for r in strong))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

fields=['scenario','request_id','channel','receiver','edge','late_injected','active_donors','primary_donor_rank',
        'primary_donor_truth_matched','donor_CFO_error_hz','guided_CFO_error_hz','guided_timing_error_samples',
        'guided_margin','guided_residual_CFO_hz','blind_recovered','blind_any_accepted','primary_accepted','primary_recovered',
        'all_proposal_accepted','all_proposal_recovered','oracle_accepted','oracle_final_CFO_error_hz']
with (HERE/'cells.csv').open('w')as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    for label,rows in groups.items():
        for r in rows:
            g=r['guided'];p=g['primary'];d=r['donor_truth_evaluation'][0]if r['donor_truth_evaluation']else None
            writer.writerow(dict(scenario=label,**{k:r[k]for k in ['request_id','channel','receiver','edge','late_injected','blind_recovered','blind_any_accepted','oracle_accepted']},
                active_donors=g['active_donors'],primary_donor_rank=p['donor_rank']if p else None,
                primary_donor_truth_matched=d['matched']if d else None,donor_CFO_error_hz=d['CFO_error_hz']if d else None,
                guided_CFO_error_hz=p['truth']['CFO_error_hz']if p else None,guided_timing_error_samples=p['truth']['timing_error_samples']if p else None,
                guided_margin=p['score']['margin']if p else None,guided_residual_CFO_hz=p['score']['residual_cfo_hz']if p else None,
                primary_accepted=g['primary_accepted'],primary_recovered=g['primary_recovered'],
                all_proposal_accepted=g['any_accepted'],all_proposal_recovered=g['any_recovered'],
                oracle_final_CFO_error_hz=r['oracle']['tracking_cfo_hz']-213456.75))

fig,axs=plt.subplots(1,2,figsize=(12,4.5))
x=np.arange(2)
for offset,key,name,color in [(-.27,'blind_recovered','Blind identity','#999'),(-.09,'primary_recovered','First-rank donor identity','#277da8'),
                             (.09,'all_proposal_recovered','All-proposal identity','#43aa8b'),(.27,'oracle_accepted','Oracle gate support','#f8961e')]:
    axs[0].bar(x+offset,[summary['recorded'][s][key]for s in ['weak_weak','strong_weak']],width=.17,label=name,color=color)
axs[0].set_xticks(x,['Weak donor / weak later','Strong donor / weak later']);axs[0].set_ylim(0,17)
axs[0].set_ylabel('RX-window cells / 16 (all wrong/no donors retained)');axs[0].legend(fontsize=8)
axs[0].set_title('Disjoint later confirmation: acceptance differs from identity')
counts=[summary['recorded']['strong_weak'][k]for k in ['correct_primary_donor','wrong_primary_donor','no_donor']]
axs[1].bar(['Correct injected donor','Other detected donor','No detected donor'],counts,color=['#43aa8b','#f8961e','#999'])
for i,c in enumerate(counts):axs[1].text(i,c+.2,str(c),ha='center')
axs[1].set_ylim(0,17);axs[1].set_ylabel('Strong/weak RX-window cells / 16')
axs[1].set_title('First gatepassing donor by earlier blind rank')
fig.tight_layout();fig.savefig(HERE/'disjoint_recovery.png',dpi=160);fig.savefig(HERE/'disjoint_recovery.pdf');plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(12,5))
for r in strong:
    if not r['guided']['primary']:continue
    d=r['donor_truth_evaluation'][0];p=r['guided']['primary'];color='#43aa8b'if d['matched']else'#f8961e'
    marker='o'if p['truth']['matched']else'x'
    axs[0].scatter(d['CFO_error_hz'],p['truth']['CFO_error_hz'],c=color,marker=marker,s=50)
    if d['matched']:axs[1].scatter(d['CFO_error_hz'],p['truth']['CFO_error_hz'],c=color,marker=marker,s=50)
axs[0].set_xscale('symlog',linthresh=50);axs[0].set_yscale('symlog',linthresh=50)
axs[0].set_xlim(-600000,600000);axs[0].set_ylim(-600000,600000)
axs[0].set_xticks([-100000,-1000,-100,0,100,1000,100000])
axs[0].set_yticks([-100000,-1000,-100,0,100,1000,100000])
axs[0].plot([-600000,600000],[-600000,600000],':',color='gray',lw=1)
axs[0].text(.03,.97,'Green: correct injected donor (11)\nOrange: other donor (4)\nNo donor: 1 (no CFO; not plotted)\no: final identity recovered; x: miss',transform=axs[0].transAxes,va='top',fontsize=9)
axs[0].set_title('All first-rank donors; symlog axes')
bin_hz=summary['frequency']['bin_spacing_hz'];xx=np.array([-50,50])
for shift in [-bin_hz,0,bin_hz]:axs[1].plot(xx,xx+shift,':',color='#777',lw=1)
for ax in axs:
    ax.axhline(100,color='#aa3333',ls='--',lw=1);ax.axhline(-100,color='#aa3333',ls='--',lw=1)
    ax.set_xlabel('Earlier donor finalized CFO error (Hz)');ax.set_ylabel('Later guided finalized CFO error (Hz)')
axs[1].set_xlim(-50,50);axs[1].set_ylim(-550,550)
axs[1].text(.02,.98,'Dashed: ±100 Hz identity tolerance\nDotted: carry donor, or ±443.892 Hz bin hop',transform=axs[1].transAxes,va='top',fontsize=9)
axs[1].set_title('Correct donors: 7/11 hop one residual-FFT bin')
fig.tight_layout();fig.savefig(HERE/'donor_to_guided_CFO.png',dpi=160);fig.savefig(HERE/'donor_to_guided_CFO.pdf');plt.close(fig)

fig,axs=plt.subplots(1,2,figsize=(11,4))
for j,(name,pretty)in enumerate([('active','Independent later nulls; fixed active donor bank'),('noise','Independent earlier and later nulls')]):
    stats=summary['nulls'][name];values=[stats['methods'][k]for k in ['blind','primary','all_proposals']]
    rates=np.array([v['empirical_fraction']for v in values])*100
    high=np.array([v['conservative_independent_average_FAR_95_upper']for v in values])*100
    axs[j].bar(np.arange(3),rates,color=['#999','#277da8','#43aa8b'])
    axs[j].errorbar(np.arange(3),rates,yerr=np.vstack((np.zeros(3),high-rates)),fmt='none',color='black',capsize=4)
    for i,v in enumerate(values):axs[j].text(i,high[i]+.4,f"{v['events']}/{stats['n']}",ha='center',fontsize=9)
    axs[j].set_xticks(np.arange(3),['Blind','First-rank guide','All-proposal guide']);axs[j].set_ylim(0,max(high)+2)
    axs[j].set_ylabel('False acceptance per later RX trial (%)');axs[j].set_title(pretty,fontsize=10)
fig.suptitle('One any-pass outcome per trial; upper whiskers are conservative 95% bounds')
fig.tight_layout();fig.savefig(HERE/'null_acceptance.png',dpi=160);fig.savefig(HERE/'null_acceptance.pdf');plt.close(fig)

lines=['# Disjoint donor/confirmation findings','',
'This is a synthetic-superposition mechanism prototype on eight inherited paired windows, both RX, CH1/4/7/8 and both pilot edges. It does not demonstrate natural pilot recovery, analog sensitivity, equal-FAR deployment, or localization improvement. No RF collection, GPS, production edit or raw IQ export occurred.','',
'Each20ms/200000sample source window splits exactly into earlier[0,100000) and later[100000,200000),10ms/7.5frames each. Source-native half-open counters, generation, original IQ digest and separate overlay-support hashes are retained. No earlier samples or padding enter later scoring. Analytic pilot phase remains continuous across the split; only amplitude changes. Each injected strength is relative to that half\'s measured native background power, not physical antenna-input SNR.','',
'First-rank guiding uses the first earlier blind candidate passing the original fractional0.025gate. It propagates timing by native counter delta and uses the measured earlier finalized CFO. All-proposal guiding independently evaluates every gatepassing donor, bounded8, and accepts on any pass. Truth never chooses either donor policy or enters their estimates; it only evaluates the fixed2sample/100Hz recovery criterion and supplies a separately labeled oracle lane.','',
'| Earlier/later pilot ratio | Blind injected identity | Primary guided identity | All-proposal guided identity | Guided any pass (primary/all) | Oracle gate support |',
'|---|---:|---:|---:|---:|---:|']
for name in labels:
    s=summary['recorded'][name]
    truth='N/A'if name in ['zero_zero','strong_zero']else None
    lines.append(f"| {name} | {truth or str(s['blind_recovered'])+'/16'} | {truth or str(s['primary_recovered'])+'/16'} | {truth or str(s['all_proposal_recovered'])+'/16'} | {s['primary_accepted']}/16 / {s['all_proposal_accepted']}/16 | {s['oracle_accepted']}/16 |")
lines += ['',
'Ratios: weak=-24dB, strong=-18dB; zero means no injection. Weak/weak and strong/weak later samples are exactly identical, confirmed by support hashes. Strong/weak improves correctly finalized injected recovery from0/16 blind to4/16 guided, while oracle gate support is16/16. Wrong donors and no donors remain in the denominator: the strong earlier half gives11 correct injected first-rank donors,4 other detected donors,1 no donor. The all-proposal policy does not add recovery here.','',
'Gate support is distinct from frequency measurement recovery. Of the11 correct earlier donors,7 pass later scoring but move to an adjacent residual-FFT bin, about±443.892Hz, failing the frozen100Hz CFO criterion. Donor timing stays propagated and donor CFO itself was within100Hz. The unchanged GLRT grid is FFT size512 over4.4microsecond symbol spacing. Even the supplied-truth oracle chooses a one-bin-wrong finalized CFO in9/16 weak later cells despite passing its gate in16/16. Prior round2 oracle figures were gate support only and must not be read as usable measurement recovery. No CFO estimator or tolerance was changed after these outcomes.','',
'The4/16 guided gatepasses on strong/zero and zero/zero recorded backgrounds can be genuine pre-existing pilots. They are not false alarms. Donor ambiguity, the one donor acquisition failure, and later frequency precision are separate limits to this mechanism. A future donor-predictive CFO prior would need independent validation of real Doppler changes and uncertainty, rather than freezing frequency because synthetic truth is constant.','',
'Null controls use genuine independent complex Gaussian later samples. The active bank has four earlier blind donor outputs, with1–3 gatepassing proposals each;64 independent later draws per bank produce256 independent confirmation RX trials. Each trial contributes one primary/all-proposal any-pass outcome, including every proposal in that policy. Separate noise-only earlier/later controls have64 independent RX trials.','',
'| Null regime | N | Blind any-pass | Primary guide | All-proposal guide |',
'|---|---:|---:|---:|---:|']
for name in ['active','noise']:
    s=summary['nulls'][name];methods=s['methods']
    lines.append(f"| {name} | {s['n']} | {methods['blind']['events']} | {methods['primary']['events']} | {methods['all_proposals']['events']} |")
lines += ['',
'The unchanged0.025gate on10ms blind searches is not calibrated to a rare false-alarm rate. These finite empirical rates do not establish equal FAR or operational improvement. Noise-only earlier halves produced no gatepassing donor, so their0/64 guided rate alone says little about confirmation with an active donor. The active bank supplies that needed conditional exposure. Bank donors are reused, but all later null vectors are independent and distinct.','',
'Exact one-sided95%binomial upper bounds are reported for each fixed donor-bank/edge/RX stratum. Pooled bounds use a conservative independent-Bernoulli KL-Chernoff bound on average conditional FAR, allowing different probabilities across banks. They do not bound non-Gaussian recording backgrounds or extrapolate to an unseen donor population. See summary.json for every bound, stratum, paired outcome and per-RX/channel result. No rolled pilot is used as a null.','',
f"Process times: preflight{load('preflight.json')['seconds']:.2f}s, recorded{recorded['seconds']:.2f}s, active null{active['seconds']:.2f}s, independent two-half null{noise['seconds']:.2f}s. Every process had580second alarm and BLAS1. Full20ms historical parity passed on all8windows. Preflight both halves had exactly matching full candidates under the unchanged production port and explicit public10ms schedule, without replacement. All64 recorded scenario RXcells and all320 null RXtrials are retained; no failed physical slots.",'',
'Files: protocol.json and panel.json freeze sources and original authority; preflight.json verifies split feasibility/parity; recorded.json retains every donor/late candidate and native support; active_null.json/noise_null.json retain every null outcome and donor bank. cells.csv and summary.json provide lean comparisons. Four guiding tests validate blind ordering, truth-free inputs, source ownership and continuous analytic phase; two additional bound tests validate finite-trial calculations. verification.json and RF_seal.json bind outcomes and sources. Reproduction requires the exact historical PYTHONPATH and existing restricted recording access. No raw IQ is included.']
(HERE/'FINDINGS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(recorded=summary['recorded'],nulls={k:{'n':v['n'],'methods':v['methods']}for k,v in summary['nulls'].items()},frequency=summary['frequency']),indent=2))
