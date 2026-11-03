"""Bounded competing-history association over frozen DS13 positive-peak groups.

Edges use the shared raw log-gain model. State adjustment and beam truncation
mean normalized retained-history weights are not calibrated posteriors.
"""
from __future__ import annotations

import argparse, csv, json, math, sys, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "2026_10_02_ds13_timing_em" / "tle-doppler-overlay"
SCANS = ("scan-fw-911c4e5db9243281", "scan-fw-ffa1cc19d8d7c09f")
sys.path.insert(0, str(HERE.parent))
import common

@dataclass
class History:
    score: float
    mean: np.ndarray
    var: np.ndarray
    last_time: np.ndarray
    assignments: tuple

def _predict(h, lane, now, stationary_sigma, timescale):
    mean=h.mean.copy(); var=h.var.copy(); last=h.last_time.copy()
    dt=0. if not np.isfinite(last[lane]) else max(0.,now-last[lane])
    rho=math.exp(-dt/timescale)
    mean[lane]*=rho
    var[lane]=rho*rho*var[lane]+stationary_sigma**2*(1-rho*rho)
    last[lane]=now
    return mean,var,last

def _choices(h, rows, residual, log_gain, *, lane, now, state, sigma, stationary_sigma, timescale, miss, top_per_row, group_cap):
    """Return bounded joint row/satellite-exclusive extensions for one group."""
    mean,var,last=_predict(h,lane,now,stationary_sigma,timescale) if state else (h.mean.copy(),h.var.copy(),h.last_time.copy())
    partial = [(0.0, frozenset(), ())]
    for r in rows:
        innovation_var = var[lane] + sigma*sigma
        center = mean[lane]
        value = log_gain[r].copy()
        if state:
            value += -.5*((residual[r]-center)**2/innovation_var-residual[r]**2/(sigma*sigma)+np.log(innovation_var/(sigma*sigma)))
        candidates = [int(s) for s in np.argsort(value)[-top_per_row:][::-1] if np.isfinite(value[s])]
        nxt = []
        for score, used, pairs in partial:
            nxt.append((score, used, pairs + ((int(r), -1),)))
            for s in candidates:
                if int(s) not in used:
                    nxt.append((score + float(value[s]) - math.log(miss), used | {int(s)}, pairs + ((int(r), int(s)),)))
        nxt.sort(key=lambda x:x[0], reverse=True)
        partial = nxt[:group_cap]
    out=[]
    for delta, _, pairs in partial:
        branch_mean=mean.copy(); branch_var=var.copy()
        if state:
            for r,s in pairs:
                if s >= 0:
                    k=branch_var[lane,s]/(branch_var[lane,s]+sigma*sigma)
                    branch_mean[lane,s] += k*(residual[r,s]-branch_mean[lane,s]); branch_var[lane,s] *= 1-k
        out.append(History(h.score+delta, branch_mean, branch_var, last, h.assignments+(pairs,)))
    return out

def track(times, groups, residual, log_gain, *, lanes=None, beam=32, state=True, sigma=200., stationary_sigma=100., timescale=30., miss=1., top_per_row=3, group_cap=32):
    order=sorted(np.unique(groups), key=lambda g:float(times[groups==g][0]))
    n_sat=residual.shape[1]
    if lanes is None: lanes=np.zeros(len(times),int)
    lanes=np.asarray(lanes,int); nlanes=int(lanes.max())+1
    histories=[History(0.,np.zeros((nlanes,n_sat)),np.full((nlanes,n_sat),stationary_sigma**2),np.full(nlanes,np.nan),())]
    for g in order:
        rows=np.flatnonzero(groups==g)
        extensions=[]
        for h in histories:
            extensions.extend(_choices(h,rows,residual,log_gain,lane=int(lanes[rows[0]]),now=float(times[rows[0]]),state=state,sigma=sigma,stationary_sigma=stationary_sigma,timescale=timescale,miss=miss,top_per_row=top_per_row,group_cap=group_cap))
        extensions.sort(key=lambda h:h.score,reverse=True)
        histories=extensions[:beam]
    return histories, order

def marginals(histories, nrows, nsat):
    scores=np.array([h.score for h in histories]); weights=np.exp(scores-scores.max()); weights/=weights.sum()
    p=np.zeros((nrows,nsat))
    for w,h in zip(weights,histories):
        for group in h.assignments:
            for r,s in group:
                if s>=0:p[r,s]+=w
    return p, weights

def load(scan):
    data=common.load_scan(scan); return data

def run_scan(scan, outdir, **settings):
    started=time.monotonic(); data=load(scan); a=data['arrays']; native=data['native_residual_hz']; log_gain=data['log_gain']
    lane=4*a['receiver']+(a['channel']-1)
    hs, order=track(a['times_s'],a['group'],native,log_gain,lanes=lane,**settings)
    p,w=marginals(hs,len(a['times_s']),len(a['catalog_numbers']))
    group_counts=[sum(s>=0 for _,s in group) for group in hs[0].assignments]
    csvpath=outdir/f"{scan}-assignments.csv"; softpath=outdir/f"{scan}-soft-marginals.csv"
    with csvpath.open('w',newline='') as f:
        z=csv.writer(f); z.writerow(('scan','row_index','catalog_number','receiver','channel','time_s','residual_hz','probability'))
        for group in hs[0].assignments:
            for r,s in group:
                if s>=0:z.writerow((data['scan'],int(r),int(a['catalog_numbers'][s]),int(a['receiver'][r]),int(a['channel'][r]),float(a['times_s'][r]),float(a['residual_hz'][r,s]),float(p[r,s])))
    with softpath.open('w',newline='') as f:
        z=csv.writer(f); z.writerow(('scan','row_index','catalog_number','receiver','channel','time_s','residual_hz','probability'))
        rr,ss=np.nonzero(p>=.01)
        for r,s in zip(rr,ss): z.writerow((data['scan'],int(r),int(a['catalog_numbers'][s]),int(a['receiver'][r]),int(a['channel'][r]),float(a['times_s'][r]),float(a['residual_hz'][r,s]),float(p[r,s])))
    raw=[]; adjusted=[]; mean=np.zeros((8,len(a['catalog_numbers']))); var=np.full_like(mean,settings['stationary_sigma']**2); last=np.full(8,np.nan)
    for group in hs[0].assignments:
        r0=group[0][0]; ln=int(lane[r0]); now=float(a['times_s'][r0])
        if settings['state']:
            dt=0 if not np.isfinite(last[ln]) else max(0,now-last[ln]); rho=math.exp(-dt/settings['timescale']); mean[ln]*=rho; var[ln]=rho*rho*var[ln]+settings['stationary_sigma']**2*(1-rho*rho); last[ln]=now
        for r,s in group:
            if s>=0:
                raw.append(native[r,s]); adjusted.append(native[r,s]-(mean[ln,s] if settings['state'] else 0.))
                if settings['state']:
                    k=var[ln,s]/(var[ln,s]+settings['sigma']**2); mean[ln,s]+=k*(native[r,s]-mean[ln,s]); var[ln,s]*=1-k
    rms=lambda x:float(np.sqrt(np.mean(np.square(x)))) if x else None
    return {'scan':data['scan'],'session':data['session'],'scope':data['scope'],'source_provenance':data['provenance'],'rows':len(a['times_s']),'positive_peak_groups':len(order),'satellites':len(a['catalog_numbers']),'p_detection':data['detection_probability'],'valid_edges':int(np.isfinite(log_gain).sum()),'retained_histories':len(hs),'best_heuristic_score':hs[0].score,'best_history_assigned_peaks':int(sum(group_counts)),'best_history_concurrent_groups':int(sum(n>=2 for n in group_counts)),'best_history_peaks_in_concurrent_groups':int(sum(n for n in group_counts if n>=2)),'best_history_unassigned_groups':int(sum(n==0 for n in group_counts)),'final_state_max_abs_hz':float(np.max(np.abs(mean))),'assigned_native_rms_raw_hz':rms(raw),'assigned_native_rms_preupdate_adjusted_hz':rms(adjusted),'effective_beam_histories':float(1/(w@w)),'exported_assignments':int(sum(group_counts)),'soft_marginal_edges_at_least_0.01':int((p>=.01).sum()),'runtime_s':time.monotonic()-started,'csv':str(csvpath),'soft_marginals_csv':str(softpath)}

def main():
    q=argparse.ArgumentParser(); q.add_argument('--beam',type=int,default=32); q.add_argument('--state-off',action='store_true'); q.add_argument('--output',type=Path,default=HERE/'results'); args=q.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    settings={'beam':args.beam,'state':not args.state_off,'sigma':200.,'stationary_sigma':100.,'timescale':30.,'miss':1.,'top_per_row':3,'group_cap':32}
    scans=[run_scan(s,args.output,**settings) for s in SCANS]
    receipt={'schema':'ds13-competing-history-mht/v1','interpretation':'frozen conditional replay of archived positive-only peak groups; not heldout evaluation','score_warning':'edges use shared raw log-gains; state-adjusted cumulative scores and beam-normalized weights are not calibrated posteriors','settings':settings,'scans':scans,'limitations':['Exact-alias duplicate copies are removed within group; no near-frequency merging is performed.','No empty detection opportunities exist in the archive; misses mean nonassignment within an observed positive group.','State is a regularized OU diagnostic prior, not a validated physical prior.','States are independent per satellite and receiver/channel lane; there is no slope or quadratic.','Candidate truncation and beam pruning can remove plausible histories.','Inputs reuse fitted archived residuals and emissions, so results are conditional/in-sample.']}
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
