"""Scientific figures for the causal longest-unassociated-track investigation."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from investigate_ds23_0268_longest_unassociated import OUT, SOURCE, CASE
from run_algo01_ds23_sample import read


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=190,bbox_inches='tight')
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
    plt.close(fig)


def main():
    track=read(OUT/'target.json');times=np.array(track['times']);values=np.array(track['values'])
    screening=read(OUT/'screen.json');diagnostics=read(OUT/'diagnostics.json')
    frozen=screening['arms']['c0']['frozen'];refined=diagnostics['arms']['c0']['refined_candidates'][0]
    polynomial=read(OUT/'polynomial_orders.json')[0]
    residual=np.array(frozen['profile_residual_hz']);free=np.array(refined['residual_hz'])
    fig,axes=plt.subplots(3,1,figsize=(13,10),sharex=True)
    axes[0].scatter(times,values/1000,s=15,color='#d83252',label='Unassociated GLRT (82 points)',zorder=4)
    axes[0].plot(times,np.array(polynomial['prediction_hz'])/1000,color='black',lw=1.3,label='Graph polynomial (degree 4)')
    axes[0].plot(times,np.array(frozen['native_prediction_hz'])/1000,color='#e29210',lw=1.5,ls='--',
                 label='64923 shared fitted orbit + frozen hardware + curve constant')
    axes[0].set_ylabel('CFO on graph alias branch (kHz)');axes[0].legend(fontsize=9)
    axes[1].plot(times,residual,'o-',ms=3,lw=.6,color='#d83252',label='Shared-family phase: 169.6 Hz RMS')
    axes[1].plot(times,free,'o-',ms=2.5,lw=.6,color='#7e43a1',alpha=.8,label='Own phase diagnostic: 142.2 Hz RMS')
    axes[1].set_ylabel('Orbit-fit residual (Hz)');axes[1].legend(fontsize=9,loc='lower left')
    free_correction=refined['free_polynomial_diagnostics_only'][2]
    axes[2].plot(times,free_correction['remaining_residual_hz'],'o-',ms=3,lw=.6,color='#257c85',
                 label='Own phase + unpenalized quadratic residual correction: 115.4 Hz RMS')
    axes[2].plot(times,free_correction['correction_hz'],color='#7e43a1',ls='--',
                 label='Additional correction (diagnostic only; not an accepted association)')
    axes[2].set_ylabel('Residual / correction (Hz)');axes[2].set_xlabel('Time from scan start (s)')
    axes[2].legend(fontsize=9,loc='lower left')
    for ax in axes:
        ax.grid(alpha=.2)
    for ax in axes[1:]:ax.axhline(0,color='black',lw=.8)
    fig.suptitle('DS23-0268 · RX1 CH3 T000 · longest unassociated curve\n'
                 '61.49–120.03 s · one graph polynomial piece · best causal candidate 64923 / STARLINK-34643',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.94));save(fig,'target_and_residuals')

    fig,axes=plt.subplots(2,3,figsize=(17,7))
    for column,(left,right) in enumerate(((60,80),(80,100),(100,120.1))):
        keep=(times>=left)&(times<=right)
        axes[0,column].scatter(times[keep],values[keep]/1000,s=24,color='#d83252',zorder=3,label='GLRT')
        axes[0,column].plot(times[keep],np.array(polynomial['prediction_hz'])[keep]/1000,color='black',label='Graph polynomial')
        axes[0,column].plot(times[keep],np.array(frozen['native_prediction_hz'])[keep]/1000,color='#e29210',ls='--',label='Expected 64923')
        axes[0,column].set_title(f'{left}–{min(right,120):g} s · {keep.sum()} points')
        axes[1,column].plot(times[keep],residual[keep],'o-',ms=4,color='#d83252',lw=.8,label='Orbit residual')
        axes[1,column].plot(times[keep],np.array(polynomial['residual_hz'])[keep],'o-',ms=3,color='#257c85',lw=.8,label='Polynomial residual')
        axes[1,column].axhline(0,color='black',lw=.8);axes[1,column].set_ylim(-500,500)
        axes[1,column].set_xlabel('Scan time (s)')
        for ax in axes[:,column]:ax.grid(alpha=.2);ax.set_xlim(left,right)
    axes[0,0].set_ylabel('CFO (kHz)');axes[1,0].set_ylabel('Residual (Hz)')
    axes[0,0].legend(fontsize=8);axes[1,0].legend(fontsize=8)
    fig.suptitle('The complete longest track in consecutive 20 s views · c = 0',fontsize=15)
    fig.tight_layout(rect=(0,0,1,.94));save(fig,'twenty_second_segments')

    fig,axes=plt.subplots(2,1,figsize=(13,9),sharex=True)
    colors=plt.get_cmap('tab10')
    for k,row in enumerate(diagnostics['arms']['c0']['family']):
        ax=axes[0 if row['channel']<=4 else 1]
        key=row['component'].split('-RF')[0].replace('DS23-0268-RX1-','')
        n=row['retained_points'];total=row['points']
        ax.plot(row['times'],row['normalized_residual_hz'],'o-',color=colors(k),ms=3,lw=.65,
                alpha=.85,label=f'{key}: {n}/{total} used in position')
    for ax,title in zip(axes,('RX1 low band','RX1 high band'),strict=True):
        ax.set_title(title);ax.axhline(0,color='black',lw=.8);ax.grid(alpha=.2)
        ax.set_ylabel('RF-normalized residual (Hz at 11.5 GHz)');ax.legend(fontsize=8)
    axes[-1].set_xlabel('Scan time (s)')
    fig.suptitle('64923 family · shared calibration and orbit · a separate constant removed per curve\n'
                 'Shown points include rejected prefixes/suffixes; labels state the actual retained counts',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.93));save(fig,'family_residuals')

    fig,axes=plt.subplots(1,2,figsize=(14,5.5))
    rows=diagnostics['arms']['c0']['refined_candidates']
    axes[0].bar([str(r['norad']) for r in rows],[r['rms_hz'] for r in rows],color=['#257c85']+['#999999']*(len(rows)-1))
    axes[0].set_yscale('log');axes[0].axhline(450,color='#d83252',ls='--',label='450 Hz RMS gate')
    axes[0].set_ylabel('RMS after exact phase refinement (Hz)');axes[0].set_xlabel('Causal NORAD candidate')
    axes[0].set_title(f"Full causal catalogue: {screening['catalogue_candidates']} candidates");axes[0].legend(fontsize=8)
    metrics=frozen['profile_noise'];n=len(times)
    labels=('Slope','Quadratic BIC','Step statistic','Lag-1 correlation')
    values_gate=np.array([metrics['slope_z']/3,metrics['quadratic_bic_gain']/10,
                          metrics['maximum_step_z']/4,abs(metrics['lag1_acf'])/(4/np.sqrt(n))])
    axes[1].barh(labels,values_gate,color='#d83252');axes[1].axvline(1,color='black',ls='--',label='Acceptance limit')
    axes[1].set_xlabel('Statistic divided by acceptance limit');axes[1].set_title('Why the existing 64923 nomination is rejected')
    axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('Identity nomination succeeds; residual compatibility fails · c = 0',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.93));save(fig,'candidate_and_failing_gates')

    if (OUT/'raw_evaluation.json').exists():
        raw=read(OUT/'raw_evaluation.json');delta=raw['arms']['c0']['delta_hz']
        fig,axes=plt.subplots(2,1,figsize=(13,7.5),sharex=True)
        axes[0].plot(times,delta,'o-',color='#257c85',ms=3,lw=.7)
        axes[0].set_ylabel('Pilot-refined minus archived CFO (Hz)')
        axes[1].plot(times,residual,'o-',ms=3,lw=.6,color='#d83252',label='Archived GLRT')
        axes[1].plot(times,raw['arms']['c0']['frozen_residual_hz'],'o-',ms=3,lw=.6,color='#257c85',label='Independent pilot refinement')
        axes[1].set_ylabel('Frozen model residual (Hz)');axes[1].set_xlabel('Scan time (s)');axes[1].legend()
        for ax in axes:ax.grid(alpha=.2);ax.axhline(0,color='black',lw=.8)
        fig.suptitle('Existing-IQ check · no TLE or position supplied to the pilot estimator\n'
                     'Original position and calibration held fixed; boundary/control failures use original CFO',fontsize=13)
        fig.tight_layout(rect=(0,0,1,.93));save(fig,'native_IQ_refinement')

    if (OUT/'shared_step.json').exists():
        step=read(OUT/'shared_step.json');s=step['arms']['c0'];tau=s['selected_time_s']
        fig,axes=plt.subplots(3,1,figsize=(13,10.5))
        for arm,color,label in (('c0','#7e43a1','$c=0$'),('fitted_c','#e29210','Fitted $c$')):
            curve=step['arms'][arm]['curve'];cost=np.array([r['cost'] for r in curve])
            axes[0].plot([r['time_s'] for r in curve],cost-cost.min(),color=color,label=label)
        axes[0].axvline(tau,color='black',ls='--');axes[0].set_ylim(0,80)
        axes[0].set_ylabel('Training loss above minimum');axes[0].set_xlabel('Candidate event time (scan seconds)')
        axes[0].set_title('Learn event from 170 other-channel observations; exclude all 82 target points')
        axes[0].legend()
        axes[1].plot(times,residual,'o-',ms=3,lw=.65,color='#d83252',label='Original: 169.6 Hz RMS')
        axes[1].plot(times,s['target_residual_hz'],'o-',ms=3,lw=.65,color='#257c85',
                     label='Predicted shared step: 92.7 Hz RMS; residual screens pass')
        if (OUT/'raw_evaluation.json').exists():
            raw=read(OUT/'raw_evaluation.json')['arms']['c0']
            axes[1].plot(times,raw['shared_step_residual_hz'],'.-',ms=3,lw=.55,alpha=.65,color='#5a9b2b',
                         label='Independent pilot CFO + same step: 87.8 Hz RMS; screens pass')
        axes[1].axvline(tau,color='black',ls='--');axes[1].set_ylabel('Target 64923 residual (Hz)')
        axes[1].set_xlabel('Scan time (s)');axes[1].set_title('Held-out longest track · RX1 CH3 T000 · all 82 points retained')
        axes[1].legend(fontsize=9,loc='lower left')
        if (OUT/'step_transfer.json').exists():
            transfer=read(OUT/'step_transfer.json')
            row=next(r for r in transfer['rows'] if '-CH5-T004-' in r['component'])
            before=row['results']['original']['candidates'][0];after=row['results']['RX1_step_from_other_family']['candidates'][0]
            axes[2].plot(row['times'],before['residual_hz'],'o-',ms=3,lw=.65,color='#d83252',
                         label=f'Original: {before["rms_hz"]:.1f} Hz RMS; screens fail')
            axes[2].plot(row['times'],after['residual_hz'],'o-',ms=3,lw=.65,color='#257c85',
                         label=f'Step transferred from 64923: {after["rms_hz"]:.1f} Hz RMS; screens pass')
            axes[2].axvline(tau,color='black',ls='--');axes[2].set_ylabel('Other-family 67935 residual (Hz)')
            axes[2].set_title('Independent satellite-family check · RX1 CH5 T004 · all 71 points')
            axes[2].set_xlabel('Scan time (s)');axes[2].legend(fontsize=9,loc='lower left')
        for ax in axes:
            ax.grid(alpha=.2)
        for ax in axes[1:]:ax.axhline(0,color='black',lw=.8)
        fig.suptitle('A shared frequency change explains the rejected tracks\n'
                     'Best grid time 108.5 s · ~347 Hz at 11.5 GHz, or ~364 Hz additive RX offset',fontsize=14)
        fig.text(.5,.012,'Conditional diagnostic: saved RF positions/calibration are fixed. Curve constants are profiled in both cases.\n'
                 'Target and independent-family evidence never fit the event. Full pipeline and benchmark are unchanged.',
                 ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.055,1,.94));save(fig,'shared_step_held_out_prediction')


if __name__=='__main__':main()
