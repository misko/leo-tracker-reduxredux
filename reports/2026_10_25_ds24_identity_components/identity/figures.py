"""Final presentation only; all scientific/report data remain sealed."""
import matplotlib.pyplot as plt
import report as r

cases=r.read('protocol.json')['cases']
results={(case,arm):r.read(case+'_'+arm+'_result.json') for case in cases for arm in r.ARMS}
fig,axes=plt.subplots(2,2,figsize=(11.7,8.1))
for axis,case in zip(axes.flat,cases):
    r.plot_panel(axis,[results[(case,arm)]['panels'][0] for arm in r.ARMS],case+': complete target source')
fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',ncol=2,fontsize=9,frameon=False)
fig.text(.5,.006,'* Archived nominee. All remaining cavity gates pass; all identities remain unqualified.\n'
         'Saved parent positions and calibration differ between c arms. Unknown is a declared broad curve, not calibrated clutter.',
         ha='center',fontsize=8)
fig.tight_layout(rect=(0,.055,1,.96))
fig.savefig(r.HERE/'candidate_identity.png',dpi=180);fig.savefig(r.HERE/'candidate_identity.pdf');plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(13.8,5.0))
for index,axis in enumerate(axes,1):
    panels=[results[('DS24-0013',arm)]['panels'][index] for arm in r.ARMS]
    held=panels[0]['entries'][1]
    source=held['component'].split('RX1-')[1].split('-RF')[0]
    r.plot_panel(axis,panels,'Held RX1 '+source+' ('+str(held['points'])+' IDs)',True)
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=2,fontsize=9,frameon=False)
fig.text(.5,.006,'Conditional density = joint(discovery, held) / density(discovery). CH2 discovery alone nominates candidates.\n'
         'All owners RX1; archived witness selection is exposed to original labels. Overlapping folds must not be summed.',
         ha='center',fontsize=8)
fig.tight_layout(rect=(0,.09,1,.92))
fig.savefig(r.HERE/'whole_owner_identity.png',dpi=180);fig.savefig(r.HERE/'whole_owner_identity.pdf');plt.close(fig)
