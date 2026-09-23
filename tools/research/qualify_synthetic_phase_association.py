"""Known-truth observation-level qualification for phase-assisted association."""

from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SEED = 20260930
C = 299_792_458.0
RF = np.array([11.2096875e9, 11.2303125e9])
BASELINE_M = 0.08
BASELINE_ANGLE = np.deg2rad(79.0)
REGIMES = ("calibrated", "frequency_mismatch", "independent_phase")


def wrap(x): return np.angle(np.exp(1j * x))


def candidate_bank(rng, truth):
    """Create Doppler-close, phase-modestly-separated candidates without observations."""
    rows = [truth]
    for sign, scale in ((1, 1), (-1, 1), (1, 2), (-1, 2)):
        row = {k: np.array(v, copy=True) for k, v in truth.items()}
        row["theta0"] += sign * scale * np.array([0.035, -0.035])
        row["omega"] += sign * scale * np.array([0.0008, -0.0008])
        row["range_rate"] += sign * scale * 0.12
        rows.append(row)
    order = rng.permutation(len(rows))
    return [rows[i] for i in order], int(np.flatnonzero(order == 0)[0])


def predictions(candidate, t, baseline_angle=BASELINE_ANGLE):
    theta = candidate["theta0"][:, None] + candidate["omega"][:, None] * t
    unit = np.stack((np.cos(theta), np.sin(theta)), axis=-1)
    b = BASELINE_M * np.array([np.cos(baseline_angle), np.sin(baseline_angle)])
    geometric = 2 * np.pi / C * RF[:, None] * (unit @ b)
    phase_dd = wrap(geometric[0] - geometric[1])
    doppler = -RF[:, None] / C * (
        candidate["range_rate"][:, None] + candidate["range_accel"][:, None] * t
    )
    return doppler, phase_dd


def simulate_unit(index, regime):
    rng = np.random.default_rng(SEED + 1009 * index)
    t = np.linspace(0, 4, 25)
    truth = dict(
        theta0=rng.uniform(-0.8, 0.8, 2), omega=rng.uniform(-0.012, 0.012, 2),
        range_rate=rng.uniform(-3500, 3500, 2), range_accel=rng.uniform(-18, 18, 2),
    )
    bank, label = candidate_bank(rng, truth)
    doppler, _ = predictions(truth, t)
    doppler += rng.normal(0, 18, doppler.shape) + rng.normal(0, 180, (2, 1))
    # Generate full receiver/source phase, then form the observable DD.
    rx_pos = np.array([[0.0, 0.0], [BASELINE_M * np.cos(BASELINE_ANGLE), BASELINE_M * np.sin(BASELINE_ANGLE)]])
    theta = truth["theta0"][:, None] + truth["omega"][:, None] * t
    unit = np.stack((np.cos(theta), np.sin(theta)), axis=-1)
    phase = np.empty((2, 2, len(t)))
    shared = np.vstack([rng.uniform(-np.pi, np.pi) + rng.normal(0, .3) * t for _ in range(2)])
    for rx in (0, 1):
        for source in (0, 1):
            geom = 2*np.pi*RF[source]/C * (unit[source] @ rx_pos[rx])
            channel = 0.0
            if regime == "frequency_mismatch": channel = (rx*2-1) * (source*2-1) * 0.32 * t
            if regime == "independent_phase": channel = np.cumsum(rng.normal(0, .55, len(t)))
            phase[rx, source] = rng.uniform(-np.pi, np.pi) + geom + shared[rx] + channel + rng.normal(0, .10, len(t))
    dd = wrap((phase[1,0]-phase[0,0])-(phase[1,1]-phase[0,1]))
    cal = np.zeros(len(t), bool); cal[rng.permutation(len(t))[:12]] = True
    return dict(index=index, regime=regime, time=t, candidates=bank, label=label,
                doppler=doppler, phase=dd, calibration=cal)


def residuals(unit, candidate, angle=BASELINE_ANGLE):
    dp, pp = predictions(candidate, unit["time"], angle)
    cal = unit["calibration"]
    offsets = np.mean(unit["doppler"][:,cal]-dp[:,cal], axis=1, keepdims=True)
    dres = (unit["doppler"]-dp-offsets)[:,~cal].ravel()
    intercept = np.angle(np.mean(np.exp(1j*(unit["phase"][cal]-pp[cal]))))
    pres = wrap(unit["phase"][~cal]-pp[~cal]-intercept)
    return dres, pres


def fit_training(units):
    d, p = [], []
    for u in units:
        dr, pr = residuals(u, u["candidates"][u["label"]]); d.extend(dr); p.extend(pr)
    ds=max(float(np.sqrt(np.mean(np.square(d)))),1e-6); ps=max(float(np.sqrt(np.mean(np.square(p)))),1e-6)
    resultant=float(abs(np.mean(np.exp(1j*np.asarray(p)))))
    return dict(doppler_sigma=ds, phase_sigma=ps, phase_resultant=resultant,
                phase_enabled=bool(resultant>=0.8 and ps<0.8))


def evaluate(units, fit):
    rows=[]
    for u in units:
        base=[]; aug=[]; control=[]
        for c in u["candidates"]:
            dr,pr=residuals(u,c); base.append(.5*np.sum((dr/fit["doppler_sigma"])**2))
            phase=.5*np.sum((pr/fit["phase_sigma"])**2) if fit["phase_enabled"] else 0.0
            aug.append(base[-1]+phase)
            _,wrong=residuals(u,c,BASELINE_ANGLE+np.pi/2); control.append(base[-1]+.5*np.sum((wrong/fit["phase_sigma"])**2))
        def metrics(loss):
            loss=np.asarray(loss); prob=np.exp(-(loss-loss.min())); prob/=prob.sum()
            rank=int(np.argsort(loss).tolist().index(u["label"])+1)
            return rank,float(-np.log(max(prob[u["label"]],1e-300)))
        br,bl=metrics(base); ar,al=metrics(aug); cr,cl=metrics(control)
        rows.append(dict(index=u["index"],label=u["label"],baseline_rank=br,augmented_rank=ar,
                         orientation_control_rank=cr,baseline_log_loss=bl,augmented_log_loss=al,
                         orientation_control_log_loss=cl))
    return rows


def summarize(rows, fit):
    return dict(fit=fit,held_units=len(rows),coverage=(1.0 if fit["phase_enabled"] else 0.0),
                baseline_top1=sum(r["baseline_rank"]==1 for r in rows)/len(rows),
                augmented_top1=sum(r["augmented_rank"]==1 for r in rows)/len(rows),
                baseline_mean_log_loss=float(np.mean([r["baseline_log_loss"] for r in rows])),
                augmented_mean_log_loss=float(np.mean([r["augmented_log_loss"] for r in rows])),
                orientation_control_mean_log_loss=float(np.mean([r["orientation_control_log_loss"] for r in rows])))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--freeze",action="store_true"); ap.add_argument("--seal",type=Path,required=True); ap.add_argument("--output",type=Path); a=ap.parse_args()
    protocol=ROOT/"reports/2026_09_23_synthetic_phase_association_protocol.md"
    sources=[Path(__file__),protocol]
    if a.freeze:
        a.seal.parent.mkdir(parents=True,exist_ok=True); a.seal.write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2)+"\n"); return
    seal=json.loads(a.seal.read_text())
    for name,want in seal.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=want: raise ValueError("sealed source changed")
    units=[simulate_unit(i,REGIMES[i%3]) for i in range(36)]
    rng=np.random.default_rng(SEED); order=rng.permutation(36); train=set(order[:18].tolist())
    result={"schema":"synthetic-phase-association/v1","seed":SEED,"train_units":sorted(train),"held_units":sorted(set(range(36))-train),"regimes":{}}
    for regime in REGIMES:
        tr=[u for u in units if u["index"] in train and u["regime"]==regime]; he=[u for u in units if u["index"] not in train and u["regime"]==regime]
        fit=fit_training(tr); rows=evaluate(he,fit); result["regimes"][regime]={"summary":summarize(rows,fit),"rows":rows}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2)+"\n")

if __name__=="__main__": main()
