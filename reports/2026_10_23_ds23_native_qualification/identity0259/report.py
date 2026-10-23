"""Summarize frozen RF-only screen outputs without selecting new hypotheses."""
from pathlib import Path
import json
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent

def main():
    compact=[]
    fig,axes=plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for suffix in ['001','002','005','006','007']:
        d=json.loads((OUT/(suffix+'.json')).read_text())
        assert d['status']=='complete'
        group=[]
        for r in d['rows']:
            original=next(c for c in r['candidates'] if c['norad']==d['fragment']['norad'])
            alt=[c for c in r['candidates'] if c['norad']!=original['norad']]
            qualified=[c for c in alt if c['physical_and_residual_qualified']]
            best=alt[0]
            row=dict(location=r['location'],arm=r['arm'],position_east_north_km=r['position_east_north_km'],
                original_score=original['score'],original_qualified=original['physical_and_residual_qualified'],original_RMS_hz=original['conditional_RMS_hz'],
                best_refined_alternative_norad=best['norad'],best_refined_alternative_qualified=best['physical_and_residual_qualified'],
                alternative_minus_original_score=best['score']-original['score'],
                qualified_alternatives=[dict(norad=c['norad'],score_difference=c['score']-original['score']) for c in qualified])
            group.append(row)
        compact.append(dict(suffix=suffix,norad=d['fragment']['norad'],receiver=d['fragment']['receiver'],channel=d['fragment']['channel'],
            points=len(d['fragment']['times']),catalogue_count=d['catalogue_count'],candidate_pool_count=len(d['candidate_pool']),seconds=d['seconds'],rows=group))
    for j,location in enumerate(['graph_parent','native_RF_endpoint']):
        for arm,offset,color in [('c0',-.13,'#285b93'),('fitted_c',.13,'#d68a25')]:
            vals=[next(r['alternative_minus_original_score'] for r in g['rows'] if r['location']==location and r['arm']==arm) for g in compact]
            axes[j].bar(np.arange(len(compact))+offset,vals,width=.25,label=arm,color=color)
        axes[j].set(xticks=np.arange(len(compact)),xticklabels=[g['suffix'] for g in compact],title=location.replace('_',' '),xlabel='Native path suffix',ylabel='Best refined alternative − original score')
        axes[j].axhline(0,color='black',lw=.8);axes[j].legend()
    fig.suptitle('Full causal bank screen; positive favors original\nAlternatives shown include failures of physical/residual gates; conditional diagnostic only')
    fig.savefig(OUT/'score_margins.png',dpi=180);plt.close(fig)
    result=dict(paths=compact,conclusion='No refined omitted candidate improves conditional RF score at either frozen RF endpoint in either c arm. 59377 qualifies for short005 but is worse by45.86–51.41 score units; no other refined alternate passes physical plus fixed-radio gates.',
        limitation='Not an exhaustive nonlinear full-catalogue proof. Calibration uses original curved family labels and original supported orbit-mode prior; uncalibrated alternatives have phase-only orbit uncertainty on a single held owner. No independent identity validation, GPS comparison, position-accuracy claim, or joint alternative position refit.')
    (OUT/'compact.json').write_text(json.dumps(result,indent=2)+'\n')
    paths=[OUT/'screen.py',OUT/'test_screen.py',OUT/'report.py',
        Path('/srv/bulk/leo/research/algo04-native-mechanisms-20261023/source/mechanism.py'),
        Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/raw/DS23-0259/result.json'),
        Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/raw/DS23-0259/native/DS23-0259.json'),
        Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/raw/DS23-0259/native/DS23-0259_persistent5s_selection.json')]
    tools=Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools')
    paths += [tools/name for name in ['probe_ds23_family_cavity_nominations.py','probe_ds23_linear_family_groups.py','ds23_family_cavity.py','ds23_predictive_linear.py']]
    (OUT/'provenance.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2)+'\n')

if __name__=='__main__':main()
