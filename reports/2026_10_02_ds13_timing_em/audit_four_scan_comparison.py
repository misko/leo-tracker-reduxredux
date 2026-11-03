"""Check serialized four-scan fits and render frozen screen coverage."""
import json
import numpy as np
from compare_four_scans import OUTPUT,THRESHOLDS,screen


def run():
    from finite_set_fit import assert_snapshot_unchanged
    from plot_all_glrt_doppler_overlay import serializable
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=OUTPUT/'comparison-v2';receipt=json.loads((out/'receipt.json').read_text())
    assert_snapshot_unchanged(receipt['source_hashes'])
    audit=[];fig,axes=plt.subplots(1,4,figsize=(17,6))
    mapfig,mapaxes=plt.subplots(1,4,figsize=(17,5))
    colors=['.5','#0072B2','#E69F00','#009E73','#CC79A7']
    for scan,ax,mapax in zip(receipt['scans'],axes,mapaxes):
        sid=scan['session'];p=.8/len(scan['candidates']);issues=[]
        for index,evaluation in enumerate(scan['evaluations']):
            fit=json.loads((out/sid/f'fit-{index:04d}.json').read_text())
            assert fit['success'] and evaluation['success']
            assert fit['detection_probability']==p
            np.testing.assert_allclose(fit['parameters'][:2],evaluation['position'],atol=1e-10)
            np.testing.assert_allclose(fit['objective'],evaluation['objective'],rtol=0,atol=1e-7)
        maxratio={}
        for t in scan['tracks']:
            if t['ratio'] is not None:maxratio[t['catalog_number']]=max(maxratio.get(t['catalog_number'],1),t['ratio'])
        ordered=sorted(maxratio,key=maxratio.get,reverse=True)
        ax.barh(range(len(ordered)),[maxratio[n] for n in ordered],color='#0072B2')
        ax.set_yticks(range(len(ordered)),[str(n) for n in ordered]);ax.invert_yaxis()
        ax.axvline(1.1,color='k',ls='--');ax.axvline(1.025,color='#D55E00',ls=':')
        ax.set_xlim(1,max(1.2,max(maxratio.values(),default=1.2)*1.03));ax.grid(axis='x',alpha=.2)
        ax.set_title(f"Scan {scan['scan_index']} · {sid[8:16]}")
        unassessed=sorted(set(scan['candidates'])-set(maxratio))
        ax.set_xlabel('Max RX linear / quadratic RMS\nUnassessed: '+', '.join(map(str,unassessed)),fontsize=9)
        for v,color in zip(scan['variants'],colors):
            assert v['policy']==screen(scan['candidates'],scan['tracks'],v['threshold'])
            if v['status']!='evaluated':issues.append('no candidates');continue
            if not v['gradient_check_passed']:issues.append(f"{v['threshold']}: finite-difference mismatch")
            if v['boundary']:issues.append(f"{v['threshold']}: search-boundary solution")
            if min(v['hessian_eigenvalues'])<=0 or v['minimum_neighbor_increase']<=0:
                issues.append(f"{v['threshold']}: not verified minimum")
            if v['start_agreement_m']>1:issues.append(f"{v['threshold']}: start disagreement >1m")
            if not all(a['success'] for a in v['attempts']):issues.append(f"{v['threshold']}: outer optimizer status")
            label='Off' if v['threshold'] is None else str(v['threshold'])
            mapax.scatter(v['best']['east_m']/1000,v['best']['north_m']/1000,color=color,s=65,label=label)
            if v['start_agreement_m']>1:
                for attempt in v['attempts']:
                    mapax.scatter(attempt['east_m']/1000,attempt['north_m']/1000,color=color,marker='x',s=100)
        mapax.scatter([0],[0],marker='+',color='k',s=130,label='Roof');mapax.axhline(0,color='.8',lw=.6);mapax.axvline(0,color='.8',lw=.6)
        mapax.set_title(f"Scan {scan['scan_index']} · {sid[8:16]}");mapax.set_xlabel('East of roof (km)');mapax.set_ylabel('North of roof (km)')
        mapax.set_aspect('equal',adjustable='datalim');mapax.grid(alpha=.2)
        audit.append(dict(session=sid,fit_count=len(scan['evaluations']),assessed_satellites=len(maxratio),
                          unassessed_satellites=unassessed,issues=issues))
    fig.suptitle('Four additional DS13 scans · frozen curvature ratios',fontsize=16)
    fig.tight_layout(rect=(0,.03,1,.94));fig.savefig(out/'curvature-ratios.png',dpi=160);plt.close(fig)
    mapaxes[0].legend(fontsize=8);mapfig.suptitle('Independent local minima · tighter filtering does not guarantee less position bias',fontsize=15)
    mapfig.text(.5,.015,'Crosses mark distinct minima found by the two starts. Dots show the lower-score result; axes differ by scan.',ha='center',fontsize=10)
    mapfig.tight_layout(rect=(0,.055,1,.94));mapfig.savefig(out/'minimum-locations.png',dpi=160);plt.close(mapfig)
    checked,panels=plt.subplots(1,3,figsize=(16,5.5))
    for scan in receipt['scans']:
        rows=[v for v in scan['variants'] if v['status']=='evaluated']
        x=[THRESHOLDS.index(v['threshold']) for v in rows]
        line,=panels[0].plot(x,[v['best']['distance_m']/1000 for v in rows],label=f"{scan['scan_index']}: {scan['session'][8:16]}")
        for i,v in zip(x,rows):
            marker='^' if v['boundary'] else '*' if v['start_agreement_m']>1 else 'o'
            panels[0].scatter(i,v['best']['distance_m']/1000,marker=marker,s=100 if marker!='o' else 35,color=line.get_color())
        panels[1].plot(x,[np.linalg.norm(v['roof_gradient_per_100m']) for v in rows],'o-',color=line.get_color())
        panels[2].plot(x,[len(v['policy']['kept']) for v in rows],'o-',color=line.get_color())
    for panel,title in zip(panels,('Best-found position distance from roof (km)','Roof score gradient magnitude / 100 m','Retained satellite candidates')):
        panel.set_title(title);panel.set_xticks(range(5),['Off','1.1','1.075','1.05','1.025'])
        panel.set_xlabel('Exclude satellite if linear / quadratic RMS > cutoff');panel.grid(alpha=.2)
    panels[0].legend(fontsize=8)
    checked.suptitle('Four additional DS13 scans · curvature filtering is not a consistent bias correction',fontsize=15)
    checked.text(.5,.055,'Triangle: search boundary, minimum not located. Star: two starts found different minima. All other points: agreeing local searches.',ha='center',fontsize=10)
    checked.text(.5,.02,'Same score and priors; fresh seed banks, no all-visible expansion. Unassessed candidates retained. Independent single-scan fits.',ha='center',fontsize=10)
    checked.tight_layout(rect=(0,.105,1,.94));checked.savefig(out/'comparison-checked.png',dpi=170);plt.close(checked)
    (out/'audit.json').write_text(json.dumps(serializable(audit),indent=2)+'\n')
    print(json.dumps(serializable(audit),indent=2))


if __name__=='__main__':run()
