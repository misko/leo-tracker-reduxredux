"""Report sealed fixed-position identity diagnostics; no model evaluation."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ('c0','fitted_c')
COLORS = ('#286fa6','#cc7229')


def read(name):
    return json.loads((HERE/name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (HERE/name).open('x') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')


def plot_panel(axis, panels, title, conditional=False):
    pool = [row['norad'] for row in panels[0]['candidates']]
    labels = [str(norad)+(' *' if index==0 else '') for index,norad in enumerate(pool)] + ['Unresolved curve']
    field = 'conditional_objective' if conditional else 'objective'
    y = np.arange(len(labels))
    maximum = 0.
    for index,(arm,panel) in enumerate(zip(ARMS,panels)):
        usable = [row for row in panel['candidates'] if row['status']=='complete' and row['numerically_qualified']]
        best = min(row[field] for row in usable)
        values = [(row[field]-best) if row['status']=='complete' else np.nan for row in panel['candidates']]
        values += [panel['null'][field]-best]
        maximum = max(maximum,max(value for value in values if np.isfinite(value)))
        axis.scatter(values,y+(index-.5)*.22,color=COLORS[index],s=24,
                     label='Saved c = 0 parent' if index==0 else 'Saved fitted-c parent',zorder=3)
    axis.axvline(0,color='black',linewidth=.7)
    axis.set_yticks(y,labels)
    axis.invert_yaxis()
    axis.set_xscale('symlog',linthresh=2)
    axis.set_xlim(-.2,maximum*1.3)
    ticks=[v for v in (0,2,20,200,2000,20000,200000,2000000) if v <= maximum*1.3]
    axis.set_xticks(ticks,[str(v) if v<1000 else str(v//1000)+'k' for v in ticks])
    axis.grid(axis='x',alpha=.2)
    axis.set_title(title,fontsize=11)
    axis.set_xlabel('Δ −2 log predictive density\nvs best candidate (log scale above 2)',fontsize=9)
    axis.tick_params(labelsize=9)


def main():
    checks = []
    for name,expected in read('RF_seal.json')['files'].items():
        checks.append(dict(test='RF sealed file unchanged',file=name,passed=sha(HERE/name)==expected))
    protocol = read('protocol.json')
    for name,expected in protocol['source_hashes'].items():
        checks.append(dict(test='frozen source/input unchanged',file=name,passed=sha(Path(name))==expected))
    results = {(case,arm):read(case+'_'+arm+'_result.json')
               for case in protocol['cases'] for arm in ARMS}
    screens = {case:read(case+'_screen.json') for case in protocol['cases']}
    rows = []; rankings = []; all_candidates = []; aliases = []; cav=[]
    for (case,arm), result in results.items():
        if result['status']!='complete':
            raise ValueError('report preserves failure explicitly; adapt presentation before running')
        cavity = result['cavity']; cav.append(dict(case=case,arm=arm,**cavity))
        for panel in result['panels']:
            field='objective' if panel['panel']=='single' else 'conditional_objective'
            complete=[row for row in panel['candidates'] if row['status']=='complete']
            ordered=sorted(complete,key=lambda row:(row[field],row['norad']))
            best,runnerup=ordered[:2]
            ranking=dict(case=case,arm=arm,panel=panel['panel'],best=best['norad'],
                         best_objective=best[field],runnerup=runnerup['norad'],
                         runnerup_minus_best=runnerup[field]-best[field],
                         null_minus_best=panel['null'][field]-best[field],
                         parent_gate_status=cavity['fixed_score_status'],
                         discovery_exposed=panel['source_exposed'],identity_qualified=False)
            rankings.append(ranking)
            aliases.append(panel['null'])
            for candidate in panel['candidates']:
                all_candidates.append(candidate);aliases.append(candidate)
                rows.append(dict(case=case,arm=arm,panel=panel['panel'],kind='physical',norad=candidate['norad'],
                                 objective=candidate.get('objective'),conditional_objective=candidate.get('conditional_objective'),
                                 qualified_numerically=candidate.get('numerically_qualified',False),
                                 alias_stable=candidate.get('alias_stable',False),
                                 gate_status=cavity['fixed_score_status'],identity_qualified=False))
            rows.append(dict(case=case,arm=arm,panel=panel['panel'],kind='unresolved_curve',norad='',
                             objective=panel['null']['objective'],conditional_objective=panel['null'].get('conditional_objective'),
                             qualified_numerically=True,alias_stable=panel['null']['alias_stable'],
                             gate_status=cavity['fixed_score_status'],identity_qualified=False))
    checks += [dict(test='all112 physical contexts numerically qualified',passed=len(all_candidates)==112 and
                    all(c['status']=='complete' and c['numerically_qualified'] for c in all_candidates)),
               dict(test='all original remaining cavity gates pass',passed=all(c['original_remaining_gates_pass'] for c in cav)),
               dict(test='all finite alias boundary/range diagnostics stable',passed=all(c['alias_stable'] for c in aliases)),
               dict(test='0012 archived competitor preserved',passed=66259 in screens['DS24-0012']['candidate_norads']),
               dict(test='no held owner used for current nomination',passed=all(not s['held_owner_IDs_exposed_to_nomination'] for s in screens.values()))]
    write('report_checks.json',dict(all_passed=all(c['passed'] for c in checks),checks=checks))
    with (HERE/'scores.csv').open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(rankings=rankings,screen_counts={k:v['catalogue_count'] for k,v in screens.items()},
                 pools={k:v['candidate_norads'] for k,v in screens.items()},
                 cavity_counts=[dict(case=c['case'],arm=c['arm'],removed_curved=len(c['removed_curved_ids']),
                                     removed_predictive=len(c['removed_predictive_ids']),
                                     parent_gate_status=c['fixed_score_status']) for c in cav],
                 candidate_contexts=len(all_candidates),all_numerically_qualified=all(c['numerically_qualified'] for c in all_candidates),
                 maximum_dense_score_error=max(c['score_error'] for c in all_candidates),
                 maximum_conditional_dense_score_error=max(c.get('conditional_score_error',0.) for c in all_candidates),
                 adaptive_checked_candidate_rows=sum('adaptive_reference' in c for c in all_candidates),
                 maximum_adaptive_score_error=max(c.get('adaptive_score_error',0.) for c in all_candidates),
                 maximum_alias_image_sum_range_error=max(c['image_sum_range_error'] for c in aliases),
                 maximum_alias_fixed_support_shift_error=max(abs(x) for c in aliases for x in c['unchanged_support_period_shift_changes']),
                 execution=read('execution.json'),identity_qualified=False,position_fits=0,GPS_used=False,
                 historical_witness_selection='0013 witnesses were frozen from archived assigned60108 rows; current shortlist does not use their data',
                 all_0013_owners_receiver='RX1')
    write('summary.json',summary)
    fig,axes=plt.subplots(2,2,figsize=(11.7,8.0))
    for axis,case in zip(axes.flat,protocol['cases']):
        panels=[results[(case,arm)]['panels'][0] for arm in ARMS]
        plot_panel(axis,panels,case+': complete target source')
    axes[0,0].legend(fontsize=8,loc='lower right')
    fig.text(.5,.006,'* Archived nominee. All remaining cavity gates pass; all identities remain unqualified.\n'
             'Saved parent positions and calibration differ between c arms. Unknown is a declared broad curve, not calibrated clutter.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.05,1,1))
    fig.savefig(HERE/'candidate_identity.png',dpi=180);fig.savefig(HERE/'candidate_identity.pdf');plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13.8,4.9))
    for index,axis in enumerate(axes,1):
        panels=[results[('DS24-0013',arm)]['panels'][index] for arm in ARMS]
        held=panels[0]['entries'][1]
        source=held['component'].split('RX1-')[1].split('-RF')[0]
        plot_panel(axis,panels,'Held RX1 '+source+' ('+str(held['points'])+' IDs)',True)
    axes[0].legend(fontsize=8,loc='lower right')
    fig.text(.5,.006,'Conditional density = joint(discovery, held) / density(discovery). CH2 discovery alone nominates candidates.\n'
             'All owners RX1; archived witness selection is exposed to original labels. Overlapping folds must not be summed.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.085,1,1))
    fig.savefig(HERE/'whole_owner_identity.png',dpi=180);fig.savefig(HERE/'whole_owner_identity.pdf');plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
