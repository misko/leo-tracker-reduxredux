"""Rebuild V16 report assets from saved artifacts; never acquire IQ or fit a model.

Run from repo root: .venv/bin/python reports/2026_10_06_v16_implementation_report/build_report.py
Requires NumPy, Matplotlib, markdown-it-py; --snapshot additionally reads the
explicit immutable installed source files through sudo -n (read-only).
"""
import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
from markdown_it import MarkdownIt

from reference_math import ALIAS_HZ, wrap, doppler, single_window_terms, timing_penalty, glrt_spectrum

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STUDY = ROOT/'reports/2026_10_04_t1_at_v1_replication'
POLISHED = STUDY/'position-score-sweep/polished'
INPUTS = Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
RELEASE = Path('/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/lib/python3.14/site-packages/leo')
BLUE, ORANGE, GRAY, GREEN = '#0072B2', '#D55E00', '#697685', '#009E73'
SCANS = [f'N{i:02}' for i in range(1,17)]
ARMS = ['fitted-c', 'zero-c']
SOURCES = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw = path.read_bytes()
    SOURCES[str(path)] = sha(raw)
    return json.loads(raw)


def save_json(name, value):
    (HERE/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def csv_write(name, rows):
    with (HERE/name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def figure_save(fig, name):
    fig.savefig(HERE/'figures'/f'{name}.png', dpi=160, bbox_inches='tight')
    fig.savefig(HERE/'figures'/f'{name}.svg', bbox_inches='tight')
    plt.close(fig)


def pipeline_figure():
    fig, ax = plt.subplots(figsize=(13,8)); ax.set(xlim=(0,13), ylim=(0,8)); ax.axis('off')
    stages = [
        ('1  Raw IQ + capture metadata', '2.5 MS/s · two RX · attested retunes\n20 ms = 50,000 complex samples', BLUE),
        ('2  Acquisition + fractional GLRT', 'Multiple frequency/epoch basins\nExact minus control margin ≥ 0.025', BLUE),
        ('3  Orbit-free refinement', 'Each candidate: frequency recentering\nAlias branches + fractional epoch search', BLUE),
        ('4  Top-one per window', 'Highest refined margin, stable tie break\n46,775 passing windows in N01–N16', BLUE),
        ('5  Known-roof calibration', 'Long-track seeds → full-window soft fit\nRX spline on supported residuals', ORANGE),
        ('6  T1-AT satellite selection', 'Full visible bank · absolute timing ±20 s\nGreedy + one-out / many-in replacement', ORANGE),
        ('7  Freeze positioning inputs', '42,610 associated windows · fixed RX baseline\nSame observations / satellite bank in both RF arms', GREEN),
        ('8  V16 position refinement', 'Soft satellite/clutter likelihood + timing priors\nIndependent 4 km searches; fit c versus c = 0', GREEN)]
    for i, (title, desc, color) in enumerate(stages):
        col, row = i//4, i%4; x, y = .25+col*6.55, 6.2-row*1.65
        ax.add_patch(FancyBboxPatch((x,y),5.85,1.3,boxstyle='round,pad=0.1',facecolor=color+'12',edgecolor=color,lw=1.4))
        ax.text(x+.18,y+1.0,title,color=color,fontsize=12,weight='bold')
        ax.text(x+.18,y+.48,desc,fontsize=10,va='center')
        if row<3:ax.annotate('',(x+2.9,y-.32),(x+2.9,y-.04),arrowprops=dict(arrowstyle='->',color=GRAY,lw=1.5))
    ax.plot([6.2,6.45,6.45],[1.91,1.91,6.82],color=GRAY,lw=1.5)
    ax.annotate('',(6.69,6.82),(6.45,6.82),arrowprops=dict(arrowstyle='->',color=GRAY,lw=1.5))
    fig.suptitle('V16 end to end: orbit-free measurements → roof-conditioned association → position score',fontsize=16)
    fig.text(.5,.015,'Blue: no satellite input. Orange: orbit and known-roof information enter. Green: fixed input population, new position fit.',ha='center',fontsize=10)
    figure_save(fig,'01-pipeline')


def detector_figure(refined):
    fig, axs = plt.subplots(1,3,figsize=(15,4.3))
    a=axs[0]
    for frame in range(15):
        t=frame/750*1000;a.broken_barh([(t+.0088,.2816)],(.2,.6),facecolors=BLUE)
    a.set(xlim=(0,20),ylim=(0,1),yticks=[],xlabel='Time within a 20 ms probe (ms)',title='64 pilot symbols per supported frame')
    a.text(10,.06,'Powers add across frames;\nnot 20 ms coherent integration',ha='center',fontsize=9)
    a=axs[1];f0=25*ALIAS_HZ/4096
    z=np.exp(2j*np.pi*f0*4.4e-6*np.arange(64))[None,:]*np.ones((15,1))
    f,p,_,_=glrt_spectrum(z);order=np.argsort(f)
    a.plot(f[order]/1000,p[order],color=BLUE)
    a.set(xlim=(-12,12),xlabel='Residual CFO (kHz)',ylabel='Normalized exact statistic',title='Synthetic tone: GLRT search shape')
    a.text(.03,.94,'4096 bins · 55.49 Hz spacing',transform=a.transAxes,va='top',fontsize=9)
    a=axs[2];row=refined['records'][0];trace=row['refinement']['trace']
    frequencies=[row['original_hz']]+[t['tracking_cfo_hz'] for t in trace]
    a.plot(range(4),np.array(frequencies)-frequencies[0],'-o',color=BLUE)
    a.set(xticks=range(4),xticklabels=['Saved','Pass 1','Pass 2','Pass 3'],ylabel='Frequency change from saved CFO (Hz)',title='Actual N01 candidate, row 0')
    a2=a.twinx();a2.plot(range(4),[row['original_margin']]+[t['margin'] for t in trace],'--s',color=ORANGE)
    a2.set_ylabel('Exact − control margin',color=ORANGE)
    fig.suptitle('Acquisition is a starting hypothesis; GLRT re-estimates frequency from the IQ',fontsize=15)
    fig.tight_layout();figure_save(fig,'02-glrt-refinement')


def candidate_figure(obs, ref):
    group=obs['records'][0]['group_id']; original=[r for r in obs['records'] if r['group_id']==group]
    byrow={r['row_index']:r for r in ref['records']}
    fig, axs=plt.subplots(1,2,figsize=(12,4.5),sharey=True)
    for a,after in zip(axs,[False,True]):
        for r in original:
            rr=byrow[r['row_index']];f=rr['output_hz'] if after else r['original_hz']
            m=rr['refinement'].get('margin',rr['original_margin']) if after else r['original_margin']
            winner=r['row_index'] in ref['top_rows']
            a.scatter(wrap(f)/1000,m,color=BLUE if winner else GRAY,s=95 if winner else 42,zorder=3)
            rank=r['candidate_rank']
            offset={0:(-20,20),1:(25,-30),2:(25,-8),3:(-20,-28),7:(25,14)}.get(rank,(15,10))
            if rank==3 and not after:offset=(-20,12)
            a.annotate(f'rank {rank}',(wrap(f)/1000,m),xytext=offset,
                textcoords='offset points',fontsize=9,ha='right' if offset[0]<0 else 'left',
                arrowprops=dict(arrowstyle='-',color=GRAY,lw=.7))
        a.set(xlabel='Wrapped candidate CFO (kHz)',ylim=(.30,.48),
            title='After orbit-free refinement' if after else 'Saved fractional GLRT candidates')
        a.grid(alpha=.15)
    axs[0].set_ylabel('GLRT margin');fig.suptitle('Actual N01 first RX0 window: several hypotheses, one retained observation',fontsize=15)
    fig.text(.5,.01,'Blue identifies the eventual top-margin candidate. Near-overlapping points can be separate records; they are not extra windows.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.05,1,.94));figure_save(fig,'03-top-one')


def calibration_figure(cal):
    t=np.linspace(0,300,301);p=np.array(cal['arms']['fitted-c']['parameters'])
    fig,axs=plt.subplots(1,2,figsize=(12,4.3))
    for rx,color in [(0,BLUE),(1,ORANGE)]:
        s=np.interp(t,cal['spline_nodes_s'],cal['correction_knots_hz'][rx])
        baseline=p[2+2*rx]+p[3+2*rx]*(t-150)+s
        axs[0].plot(t,baseline,label=f'RX{rx}',color=color)
        axs[1].plot(t,s,label=f'RX{rx}',color=color)
    axs[0].set(title='Fixed receiver baseline: line + nonlinear correction',ylabel='Hz',xlabel='Receive time (s)')
    axs[1].set(title='Nonlinear correction alone (piecewise linear)',ylabel='Hz',xlabel='Receive time (s)')
    for a in axs:a.grid(alpha=.18);a.legend()
    fig.suptitle(f"Actual N01 calibration: {cal['spline_training_rows']:,} supported spline-training windows",fontsize=15)
    fig.tight_layout();figure_save(fig,'04-calibration')


def coverage_figure(rows):
    fig,axs=plt.subplots(1,2,figsize=(14,5))
    x=np.arange(16);a=axs[0]
    den=np.array([r['passing_windows'] for r in rows]);g=np.array([r['greedy_windows'] for r in rows]);final=np.array([r['associated_windows'] for r in rows])
    a.bar(x,g/den*100,color=BLUE,label='Greedy')
    a.bar(x,(final-g)/den*100,bottom=g/den*100,color=GREEN,label='Net replacement change')
    a.axhline(90,color=GRAY,ls=':',lw=1)
    a.set(xticks=x,xticklabels=SCANS,ylim=(0,103),ylabel='% of passing top-one windows',title='Frozen fitted-c association input population')
    a.tick_params(axis='x',rotation=60);a.legend(fontsize=9)
    a=axs[1];a.axis('off')
    a.text(.03,.96,'Greedy + replacement',va='top',fontsize=16,color=BLUE,weight='bold')
    a.text(.03,.83,'1  Add the mode explaining most free coherent windows.\n\n2  Require its gain to exceed 10 windows per satellite.\n\n3  Remove one chosen satellite; release its windows.\n\n4  Greedily add one or more alternatives.\n\n5  Accept only if Nassigned − 10 × Nsat increases.\n\n6  Stop after a no-improvement pass (cap: 3 passes).',va='top',fontsize=12)
    fig.suptitle('Association is discrete coverage optimization—not the final position likelihood',fontsize=16)
    fig.tight_layout();figure_save(fig,'05-association')


def likelihood_figure():
    fig,axs=plt.subplots(1,3,figsize=(14,4.3));e=np.linspace(-800,800,401)
    for k,color in [(10,BLUE),(30,ORANGE)]:
        mu=np.full((len(e),k),50000.);mu[:,0]=-e
        _,z,clutter,_=single_window_terms(np.zeros(len(e)),mu,np.ones_like(mu,bool))
        axs[0].plot(e,z[:,0],color=color,label=f'{k} selected satellites')
    axs[0].set(xlabel='Residual to a single nearby satellite (Hz)',ylabel='Responsibility',title='Soft support, not a ±600 Hz cut');axs[0].legend(fontsize=9)
    for second,label,color in [(50000,'One nearby match',BLUE),(0,'Two equally good matches',ORANGE)]:
        mu=np.full((len(e),30),50000.);mu[:,0]=-e;mu[:,1]=second-e
        _,z,_,_=single_window_terms(np.zeros(len(e)),mu,np.ones_like(mu,bool))
        axs[1].plot(e,z[:,0],label=label,color=color)
    axs[1].set(xlabel='Residual (Hz)',ylabel='Responsibility of satellite 1',title='Competing matches share probability');axs[1].legend(fontsize=9)
    d=np.linspace(-1,1,301)
    axs[2].plot(d,.5*(d/.15)**2,label='V16: relative sigma 0.15 s',color=BLUE)
    axs[2].plot(d,.5*(d/(1/3))**2,label='C1: relative sigma 1/3 s',color=ORANGE)
    axs[2].set(xlabel='One relative timing coordinate (s)',ylabel='Gaussian penalty contribution',title='Soft prior ≠ hard timing limit');axs[2].legend(fontsize=8)
    for a in axs:a.grid(alpha=.15)
    fig.suptitle('V16 likelihood and priors: controlled numerical illustrations, not additional fits',fontsize=15)
    fig.tight_layout();figure_save(fig,'06-likelihood')


def result_figure(results):
    fig,axs=plt.subplots(2,2,figsize=(14,9))
    for col,arm in enumerate(ARMS):
        x=np.arange(16);a=axs[0,col]
        for mode,color in [('C1',GRAY),('V16',BLUE if col==0 else ORANGE)]:
            rr=[r for r in results if r['arm']==arm and r['mode']==mode]
            a.plot(x,[r['distance_m'] for r in rr],'-o',color=color,label=mode)
            for i,r in enumerate(rr):
                if r['boundary']:a.scatter(i,r['distance_m'],marker='^',s=100,facecolor=color,edgecolor='black',zorder=4)
                if not r['converged']:a.scatter(i,r['distance_m'],marker='x',s=70,color='black',zorder=5)
        a.set(xticks=x,xticklabels=SCANS,ylabel='Position error (m)',ylim=(0,4300),title='Fitted c' if col==0 else 'c = 0')
        a.tick_params(axis='x',rotation=60);a.axhline(4000,color=GRAY,ls=':');a.legend()
        a=axs[1,col];rr=[r for r in results if r['arm']==arm and r['mode']=='V16']
        a.scatter([r['posterior_rms_hz'] for r in rr],[r['distance_m'] for r in rr],color=BLUE if col==0 else ORANGE)
        for r in rr:a.annotate(r['scan'],(r['posterior_rms_hz'],r['distance_m']),xytext=(4,4),textcoords='offset points',fontsize=8)
        a.set(xlabel='Posterior-weighted residual RMS (Hz)',ylabel='Position error (m)',title='V16: frequency fit is not location accuracy')
    for a in axs.ravel():a.grid(alpha=.17)
    fig.suptitle('Saved N01–N16 results · matched inputs, priors and search budgets within each RF comparison',fontsize=15)
    fig.text(.5,.01,'Triangle: 4 km boundary. ×: stationarity criterion not met. No new model fits generated for this report.',ha='center')
    fig.tight_layout(rect=(0,.03,1,.95));figure_save(fig,'07-results')


def position_figure(data, result, mu, responsibilities):
    fig,axs=plt.subplots(1,2,figsize=(13,5))
    a=axs[0]
    for arm,color in zip(ARMS,[BLUE,ORANGE]):
        for scan in SCANS:
            r=read(POLISHED/f'{scan}-{arm}-V16.json');x,y=r['best']['point_km']
            a.scatter(x,y,color=color,marker='^' if r['boundary'] else 'o',s=35)
            if scan in {'N01','N05','N09','N16'}:
                a.annotate(scan,(x,y),xytext=(3,3),textcoords='offset points',fontsize=8,color=color)
        a.plot([],[],'.',color=color,label=arm)
    t=np.linspace(0,2*np.pi,300);a.plot(4*np.cos(t),4*np.sin(t),':',color=GRAY)
    a.scatter(0,0,marker='+',s=180,color='black');a.set_aspect('equal')
    a.set(xlabel='East of known roof (km)',ylabel='North of known roof (km)',title='Independent V16 best-found positions')
    a.legend(fontsize=8)
    a=axs[1];winner=responsibilities.argmax(axis=1);idx=np.arange(len(mu));r=wrap(data['measured']-mu[idx,winner]);strong=responsibilities[idx,winner]>.5
    for rx,color in [(0,BLUE),(1,ORANGE)]:
        keep=strong&(data['receiver']==rx);a.scatter(data['times'][keep],r[keep],s=7,alpha=.45,label=f'RX{rx}',color=color)
    a.axhline(0,color=GRAY,lw=.8);a.set(xlabel='Receive time (s)',ylabel='Residual to top-responsibility satellite (Hz)',
        title='N01 fitted c: strong soft matches only')
    a.legend(fontsize=9);a.grid(alpha=.15)
    fig.suptitle('Position output and frequency residuals are different diagnostics',fontsize=15)
    fig.text(.5,.015,'Left: selected scan labels; all 16 scans shown in each arm. Right: responsibility > 0.5 shown; all input windows enter the loss.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.95));figure_save(fig,'08-position-output')


def snapshot():
    installed = ['analysis/starlink/'+n+'.py' for n in ['acquisition','pilot_methods','fractional_epoch','templates','pilot_search_geometry']]
    installed += ['scanner/detector.py','scanner/adaptive_hop_analysis.py','application/scanner_trajectory.py',
        'application/persistent_hop_trajectory.py','analysis/persistent_hop_trajectory.py','analysis/cfo_lines.py',
        'analysis/adaptive_tle_prediction.py','sky/frames.py','sky/propagation.py']
    research = {
        '2026_10_04_ds13_18_scan_benchmark':['export_observations','run_refinement','refinement','numeric_data','orbit_bank','bootstrap_tracks','seed_timing_variant','cohort','constrained_fit'],
        '2026_10_04_t1_at_v1_replication':['full_data_calibration','seed_restart_pipeline','refit_full_calibration_seeds','full_data_localization','position_score_sweep','polish_position_score_sweep','convergence_fisher','timing_penalty_variants'],
        '2026_10_02_multiscan_localization':['finite_set_likelihood','prediction_jacobian','joint_inputs','track_seed','staged_fit'],
        '2026_10_02_ds13_timing_em':['timing_model','rf_calibration_diagnostic'],
        '2026_10_03_ds13_coverage_goal':['receiver_spline','adaptive_discovery'],
    }
    inventory=[]
    with zipfile.ZipFile(HERE/'implementation-sources.zip','w',zipfile.ZIP_DEFLATED) as archive:
        def add(name,path,raw):
            info=zipfile.ZipInfo(name,date_time=(2026,10,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,raw); inventory.append(dict(member=name,source=str(path),sha256=sha(raw)))
        for name in installed:
            path=RELEASE/name;raw=subprocess.check_output(['sudo','-n','/bin/cat',str(path)])
            add('installed-leo/'+name,path,raw)
            if name.endswith('/templates.py'):
                tree=ast.parse(raw)
                for node in tree.body:
                    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='QIN_EDGE_PILOT_HEX_V1' for t in node.targets):
                        save_json('pilot-states.json',ast.literal_eval(node.value))
        for folder,names in research.items():
            for n in names:
                path=ROOT/'reports'/folder/(n+'.py');add('research/'+folder+'/'+path.name,path,path.read_bytes())
        for n in ['greedy_restart_scan','greedy_pool_two_scans','penalty_replace_search']:
            path=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')/(n+'.py');add('association/'+path.name,path,path.read_bytes())
    save_json('implementation-sources.json',inventory)


def html_report():
    source=(HERE/'report.md').read_text()
    math=[]
    def protect(match):
        math.append(match.group(0));return f'V16MATHPLACEHOLDER{len(math)-1}END'
    source=re.sub(r'\\\[.*?\\\]|\\\(.*?\\\)',protect,source,flags=re.S)
    body=MarkdownIt('commonmark',{'html':True}).enable('table').render(source)
    for i,value in enumerate(math):body=body.replace(f'V16MATHPLACEHOLDER{i}END',value)
    contents=[]
    def heading(match):
        title=match.group(1)
        slug=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')
        contents.append(f'<li><a href="#{slug}">{title}</a></li>')
        return f'<h2 id="{slug}">{title}</h2>'
    body=re.sub(r'<h2>(.*?)</h2>',heading,body)
    navigation='<details class="contents"><summary>Contents</summary><ul>'+''.join(contents)+'</ul></details>'
    body=body.replace('</h1>','</h1>'+navigation,1)
    template='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V16: from IQ to position</title><style>
body{font:17px/1.65 system-ui,sans-serif;max-width:1080px;margin:48px auto;padding:0 28px;color:#243345}
h1,h2,h3{line-height:1.25;color:#123955}h1{font-size:2.5em}h2{margin-top:2.2em;border-top:1px solid #ddd;padding-top:1em}
a{color:#0072b2}img{max-width:100%}table{border-collapse:collapse;width:100%;font-size:.88em;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #d7dfe5;padding:8px;text-align:left}th{background:#edf4f9}pre{background:#eff3f6;padding:20px;overflow:auto;font-size:.82em}
blockquote{border-left:4px solid #0072b2;margin-left:0;padding-left:20px;color:#43596b}code{font-size:.9em}
.contents{background:#edf4f9;padding:12px 20px}.contents summary{cursor:pointer;font-weight:600}.contents ul{columns:2;font-size:.9em}
@media print{body{max-width:none;font-size:10pt}h2{break-before:auto}img,table{break-inside:avoid}}
</style><script>window.MathJax={tex:{inlineMath:[['\\\\(','\\\\)']],displayMath:[['\\\\[','\\\\]']]}};</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script><body>'''
    (HERE/'report.html').write_text(template+body+'<hr><p>Equations use MathJax when online; report.md always contains their complete LaTeX source.</p></body></html>')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',action='store_true');args=parser.parse_args()
    (HERE/'figures').mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    rows=[];results=[];checks=[]
    for scan in SCANS:
        obs=read(INPUTS/scan/'observations.json');ref=read(INPUTS/scan/'refinement/refined.json')
        assoc=read(STUDY/'full-scan-seed-restart'/scan/'associations/fitted-c.json')
        cal=read(STUDY/'full-scan-seed-restart'/scan/'calibration.json')
        source=read(STUDY/'full-scan-seed-restart/positions'/scan/'result.json')
        path=STUDY/'full-scan-seed-restart/positions'/scan/'result.npz'
        digest=sha(path.read_bytes());SOURCES[str(path)]=digest
        assert source['input_sha256'].removeprefix('sha256:')==digest
        with np.load(path,allow_pickle=False) as z:data={k:z[k].copy() for k in z.files}
        rows.append(dict(scan=scan,session_id=obs['summary']['session_id'],sample_rate_hz=obs['summary']['sample_rate_hz'],
            passing_candidates=len(obs['records']),passing_windows=obs['summary']['passing_windows'],
            associated_windows=assoc['final']['assigned'],greedy_windows=assoc['initial']['assigned'],
            satellites=assoc['final']['satellites'],spline_training_windows=cal['spline_training_rows']))
        for mode in ['C1','V16']:
            for arm in ARMS:
                result=read(POLISHED/f'{scan}-{arm}-{mode}.json')
                assert result['input_sha256'].removeprefix('sha256:')==digest
                assert result['fit_original_rows']==result['evaluation_original_rows']==data['original_rows'].tolist()
                assert not result['heldout_original_rows']
                results.append(dict(scan=scan,arm=arm,mode=mode,distance_m=result['distance_m'],
                    converged=result['converged'],boundary=result['boundary'],windows=result['windows'],satellites=len(result['numbers']),
                    posterior_rms_hz=result['posterior_weighted_residual_rms_hz'],owner_rms_hz=result['owner_rms_hz'],
                    mean_signal_posterior=result['mean_signal_posterior'],data_nll=result['data_nll'],timing_prior_nll=result['timing_prior_nll']))
                if mode=='V16':
                    parameters=np.array(result['best']['parameters']);coefficient=result['best']['coefficient']
                    mu,visible=doppler(data,parameters,source['input_metadata']['rf_center_hz'],coefficient)
                    log_l,z,clutter,grad=single_window_terms(data['measured'],mu,visible)
                    tau=parameters[6:].mean();delta=parameters[6:]-tau
                    objective=-log_l.sum()+timing_penalty(tau,delta)
                    rms=np.sqrt(np.sum(z*wrap(data['measured'][:,None]-mu)**2)/np.sum(z))
                    checks.append(dict(scan=scan,arm=arm,windows=len(mu),objective_error=abs(objective-result['objective']),
                        posterior_rms_error_hz=abs(rms-result['posterior_weighted_residual_rms_hz'])))
                    if scan=='N01' and arm=='fitted-c':position_figure(data,result,mu,z)
        if scan=='N01':
            detector_figure(ref);candidate_figure(obs,ref);calibration_figure(cal)
    pipeline_figure();coverage_figure(rows);likelihood_figure();result_figure(results)
    csv_write('cohort.csv',rows);csv_write('results.csv',results)
    summary={}
    for mode in ['C1','V16']:
        for arm in ARMS:
            rr=[r for r in results if r['mode']==mode and r['arm']==arm];errors=np.array([r['distance_m'] for r in rr])
            summary[f'{mode}/{arm}']=dict(median_m=float(np.median(errors)),mean_m=float(np.mean(errors)),p90_m=float(np.quantile(errors,.9)),
                below_1km=int(sum(errors<1000)),converged=sum(r['converged'] for r in rr),boundary=sum(r['boundary'] for r in rr),
                median_posterior_rms_hz=float(np.median([r['posterior_rms_hz'] for r in rr])))
    save_json('summary.json',summary)
    check=dict(scan='N01',windows=2444,cases=checks,maximum_objective_error=max(r['objective_error'] for r in checks),
        maximum_posterior_rms_error_hz=max(r['posterior_rms_error_hz'] for r in checks),scope='Independent NumPy equations against all 32 saved V16 results; no fitting.')
    save_json('numerical-check.json',check);print(json.dumps({k:v for k,v in check.items() if k!='cases'},indent=2))
    if check['maximum_objective_error']>1e-7 or check['maximum_posterior_rms_error_hz']>1e-7:raise ValueError('Independent numerical reproduction failed')
    save_json('source-manifest.json',SOURCES)
    if args.snapshot:snapshot()
    if (HERE/'report.md').exists():html_report()


if __name__=='__main__':main()
