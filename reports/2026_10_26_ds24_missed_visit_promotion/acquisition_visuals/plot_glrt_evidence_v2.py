"""Read-only scientific plots of sealed GLRT points, without IQ or geography."""
import collections
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'broader'
EXPECTED_CLOSURE = 'dfbac175cf3d0c0474ab3ac105be6d900d43affc6e754e39ba11fccf64666da9'
CATEGORIES = ['original', 'new_curved', 'new_other_graph', 'new_outside_graph']
STYLES = {
    'original': dict(color='#8b9196', marker='o', s=15, alpha=.68, linewidths=0, zorder=2),
    'new_curved': dict(color='#148348', marker='o', s=39, alpha=1, edgecolors='white', linewidths=.5, zorder=5),
    'new_other_graph': dict(color='#dc8706', marker='^', s=44, alpha=1, edgecolors='white', linewidths=.5, zorder=6),
    'new_outside_graph': dict(color='#cb353b', marker='x', s=38, alpha=1, linewidths=1.25, zorder=7),
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write(path, obj):
    with Path(path).open('x') as f:
        json.dump(obj, f, indent=2, allow_nan=False); f.write('\n')

def verified_inputs():
    closure = SOURCE/'closure_seal.json'
    assert sha(closure) == EXPECTED_CLOSURE, 'sealed input closure changed'
    checked = {str(closure): sha(closure)}
    for path, h in read(closure)['files'].items():
        assert sha(path) == h, path
        checked[path] = h
    sealed = read(SOURCE/'artifact_seal.json')['files']
    # Verify every artifact bound by the acquisition seal, without following raw
    # input/segment references or opening position reports.
    for path, h in sealed.items():
        assert sha(path) == h, path
        checked[path] = h
    return checked, sealed

def points_for_block(block, original, observations, tracks, audit, ledger):
    original_by_id = {r['observation_id']: r for r in original}
    all_by_id = {r['observation_id']: r for r in observations}
    assert len(all_by_id) == len(observations)
    assert observations[:len(original)] == original
    new_ids = set(all_by_id)-set(original_by_id)
    graph_ids = {oid for t in tracks for oid in t['observation_ids']}
    curved_ids = set(audit['new_curved_ids'])
    assert curved_ids <= new_ids & graph_ids
    assert new_ids == {r['target_observation_id'] for r in ledger['staged']}
    native_by_id = {r['target_observation_id']: r['native'] for r in ledger['staged']}
    seed = block['seed_native']; fs = seed['sample_rate_hz']
    center = block['center_counter']; seed_time = seed['time_s']
    lo, hi = [(counter-center)/fs for counter in block['clipped_interval_closed']]
    assert block['requested_interval_closed'] == [center-12*fs, center+12*fs]
    panels = []
    for rx in [0, 1]:
        points = []
        for row in observations:
            if row['native_receiver_id'] != rx or row['channel'] != block['channel']:
                continue
            dt = row['time_s']-seed_time
            if not lo-1e-8 <= dt <= hi+1e-8:
                continue
            oid = row['observation_id']
            if oid in original_by_id:
                assert row == original_by_id[oid]
                category = 'original'
            else:
                n = native_by_id[oid]
                assert n['edge'] == block['edge']
                assert abs(dt-(((n['start_counter']+n['stop_counter'])/2-center)/fs)) < 1e-7
                category = 'new_curved' if oid in curved_ids else ('new_other_graph' if oid in graph_ids else 'new_outside_graph')
            points.append(dict(observation_id=oid, time_from_seed_s=dt, recording_time_s=row['time_s'],
                measured_cfo_hz=row['measured_cfo_hz'], category=category,
                native_receiver_id=rx, channel=row['channel']))
        counts = collections.Counter(r['category'] for r in points)
        panels.append(dict(receiver_label=f'RX{rx+1}', native_receiver_id=rx,
            counts={key:counts[key] for key in CATEGORIES}, points=points))
    return dict(block_id=block['block_id'], case=block['case'], channel=block['channel'],
        edge=block['edge'], nominating_native_receiver_id=block['nominating_receiver_id'],
        seed_observation_id=block['seed_observation_id'], seed_recording_time_s=seed_time,
        plotted_interval_from_seed_s=[lo,hi], plotted_recording_interval_s=[seed_time+lo,seed_time+hi],
        native_counter_interval_closed=block['clipped_interval_closed'],
        exact_24s_interval=abs(hi-lo-24)<1e-9, retained_paired_windows=block['retained_paired_visits'],
        capped=block['capped'], panels=panels)

def plot(cohort, blocks):
    plt.rcParams.update({'font.size':10, 'axes.titlesize':11, 'axes.labelsize':10,
        'font.family':'DejaVu Sans', 'pdf.fonttype':42, 'ps.fonttype':42,
        'axes.spines.top':False, 'axes.spines.right':False})
    fig, axes = plt.subplots(len(blocks), 2, figsize=(13.2, 2.65*len(blocks)+1.8),
        squeeze=False, sharex=True)
    title = 'Reserved scans' if cohort=='reserved' else 'Previously exposed development scans'
    fig.suptitle(title+' · GLRT evidence in nominated coherent blocks', x=.5, y=.987, fontsize=16, weight='bold')
    legend = [
        Line2D([],[],ls='',marker='o',color=STYLES['original']['color'],markersize=5,label='Original GLRT'),
        Line2D([],[],ls='',marker='o',color=STYLES['new_curved']['color'],markersize=6,label='New · curved graph'),
        Line2D([],[],ls='',marker='^',color=STYLES['new_other_graph']['color'],markersize=6,label='New · other graph'),
        Line2D([],[],ls='',marker='x',color=STYLES['new_outside_graph']['color'],markersize=6,label='New · outside graph'),
    ]
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.966),ncol=4,frameon=False,fontsize=10)
    for i, block in enumerate(blocks):
        all_cfo = [r['measured_cfo_hz']/1000 for panel in block['panels'] for r in panel['points']]
        bottom, top = min(all_cfo,default=0), max(all_cfo,default=1)
        padding = max((top-bottom)*.12, 3)
        for j, panel in enumerate(block['panels']):
            ax = axes[i,j]
            for key in CATEGORIES:
                selected = [r for r in panel['points'] if r['category']==key]
                ax.scatter([r['time_from_seed_s'] for r in selected],
                    [r['measured_cfo_hz']/1000 for r in selected], **STYLES[key])
            ax.set_xlim(block['plotted_interval_from_seed_s'])
            ax.set_ylim(bottom-padding,top+padding)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.grid(True, color='#e7e9eb', linewidth=.65, zorder=0)
            ax.set_axisbelow(True)
            count = panel['counts']
            label = 'Original {} | New: {} curved, {} other, {} outside'.format(*[count[k] for k in CATEGORIES])
            start,stop=block['plotted_recording_interval_s']
            ax.set_title(f"{block['case']} · CH{block['channel']} · {panel['receiver_label']} (native {j})\n"
                f"Recording time {start:.3f}–{stop:.3f} s\n{label}", loc='left',pad=7,fontsize=10.4)
            if j==0:ax.set_ylabel('Measured CFO (kHz)')
            ax.set_xticks([-12,-8,-4,0,4,8,12])
            if i==len(blocks)-1:ax.set_xlabel('Time from nominating seed midpoint (s)')
    fig.text(.5,.016,
        'Native measured CFO branches are shown as stored; possible aliases/wraps are unresolved. No unwrapping or fitted satellite curves.\n'
        'Graph classification uses the full recording; points are displayed only within the selected channel and exact nominated interval.',
        ha='center',va='bottom',fontsize=9,color='#444a50')
    fig.subplots_adjust(left=.075,right=.985,bottom=.066,top=.92 if len(blocks)==6 else .938,hspace=.80,wspace=.17)
    prefix = HERE/(cohort+'_glrt_blocks_v2')
    fig.savefig(str(prefix)+'.png',dpi=190,facecolor='white')
    fig.savefig(str(prefix)+'.pdf',facecolor='white',metadata={'Title':title+' GLRT evidence','Subject':'Sealed native GLRT points, no IQ or geographic inference'})
    plt.close(fig)
    return [Path(str(prefix)+'.png'),Path(str(prefix)+'.pdf')]

def main():
    checked,sealed=verified_inputs()
    nomination=read(SOURCE/'nominations.json');cohorts={r['case']:r['cohort'] for r in nomination['cases']}
    used={str(SOURCE/'nominations.json'):sha(SOURCE/'nominations.json')};cache={};blocks=[]
    for block in nomination['blocks']:
        case=block['case']
        if case not in cache:
            folder=SOURCE/'graphs'/case
            audit_path=folder/'audit.json';ledger_path=SOURCE/'ledgers'/(case+'_additions.json')
            original_path=Path(next(p for p in nomination['source_inputs'] if p.endswith('/'+case+'/observations.json')))
            original_digest=nomination['source_inputs'][str(original_path)]
            assert sha(original_path)==original_digest
            paths=[original_path,folder/'observations.json',folder/'tracks.json',audit_path,ledger_path]
            for path in paths:
                digest=sha(path)
                if path!=original_path:assert sealed[str(path)]==digest
                used[str(path)]=digest
            cache[case]=[read(p) for p in paths]
        original,observations,tracks,audit,ledger=cache[case]
        rendered=points_for_block(block,original,observations,tracks,audit,ledger)
        rendered['cohort']=cohorts[case];blocks.append(rendered)
    assert len([b for b in blocks if b['cohort']=='reserved'])==6
    assert len([b for b in blocks if b['cohort']=='development'])==8
    assert all(b['exact_24s_interval'] for b in blocks)
    write(HERE/'plotted_points_v2.json',dict(blocks=blocks,frequency_transform='Hz / 1000 only; no alias or unwrap transform'))
    outputs=[];counts={}
    for cohort in ['reserved','development']:
        chosen=[b for b in blocks if b['cohort']==cohort]
        outputs.extend(plot(cohort,chosen))
        counter=collections.Counter()
        for b in chosen:
            for p in b['panels']:counter.update(p['counts'])
        counts[cohort]=dict(counter)
    # Input files are read-only throughout; verify their hashes again after rendering.
    for path,h in checked.items():assert sha(path)==h,path
    for path,h in used.items():assert sha(path)==h,path
    manifest=dict(all_passed=True,source_closure_sha256=EXPECTED_CLOSURE,
        input_seals_and_all_bound_artifact_hashes_verified_before_and_after=True,
        verified_bound_artifacts=len(checked),used_inputs=used,cohort_counts=counts,
        reserved_blocks=6,development_blocks=8,receiver_columns=['RX1 (native 0)','RX2 (native 1)'],
        classifications={'original':'original accepted GLRT owner',
            'new_curved':'new owner retained in actively curved graph support',
            'new_other_graph':'new owner retained in other graph support',
            'new_outside_graph':'new admitted owner outside retained RF graph'},
        x_interval='exact closed nominated 24s counter interval, displayed relative to native seed midpoint',
        y_values='stored measured_cfo_hz / 1000, no unwrap/alias correction or fitted curves',
        no_IQ_reads=True,no_position_or_GPS_inputs=True,
        figures={str(p):sha(p) for p in outputs},
        source_script_sha256=sha(__file__),plotted_points_sha256=sha(HERE/'plotted_points_v2.json'),
        python=sys.version.split()[0],matplotlib=matplotlib.__version__)
    write(HERE/'manifest_v2.json',manifest)
    print(json.dumps(dict(counts=counts,outputs=[str(p) for p in outputs],manifest_sha256=sha(HERE/'manifest_v2.json'))))

if __name__=='__main__':main()
