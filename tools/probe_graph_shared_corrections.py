"""Independent-family event nomination and bounded shared receiver trials."""

import argparse
from pathlib import Path
import numpy as np

import debug_fast_graph_unassociated as report
from probe_graph_shared_high_channels import context, select_targets, inventory, trial, figures


def nominate_event(d, targets, candidate):
    from investigate_ds23_0268_remaining_tracks import family_frequency, corrected_observation
    from leo.analysis.research.retained_track_likelihood import profile
    p, x = d["problems"]["c0"]
    c = p.calculate(x)
    scan = d["scan"]
    lo = max(scan.tracks[p.members[k]]["times"].min() for k in targets)+5
    hi = min(scan.tracks[p.members[k]]["times"].max() for k in targets)-5
    rows = []
    for k, (r, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        t = scan.tracks[i]
        if t["receiver"] != 1 or r["candidate_norad"] == candidate or not p.keep[sl].any(): continue
        active = p.keep[sl]; times = t["times"][active]
        q = t["rf_hz"]/11.5e9
        f, _ = family_frequency(p, x, r["candidate_index"], times=t["times"])
        terms = profile(corrected_observation(p, x, i), q*f, *scan.white[i])
        sigma = p.point_noise[sl][active]/np.sqrt(d["powers"][k]*c["noise_precision"][k])
        rows.append(dict(component=t["key"], norad=r["candidate_norad"], channel=t["channel"],
            times=times, residual=terms["residual"][0][active], sigma=sigma, q=q))
    offers=[]
    grid=np.arange(np.ceil(lo),np.floor(hi)+.01,1.)
    for tau in grid:
        information, cross, parts = 1., 0., []
        for row in rows:
            t=row["times"]
            if sum(t<tau)<4 or sum(t>=tau)<4: continue
            w=1/row["sigma"]
            affine=np.column_stack((np.ones(len(t)),t-t.mean()))*w[:,None]
            y=row["residual"]*w
            u=(t>=tau)*row["q"]*300*w
            y-=affine@np.linalg.lstsq(affine,y,rcond=None)[0]
            u-=affine@np.linalg.lstsq(affine,u,rcond=None)[0]
            info=float(u@u); rhs=float(u@y); information+=info; cross+=rhs
            parts.append(dict(component=row["component"],norad=row["norad"],channel=row["channel"],
                information=info,amplitude_hz=300*rhs/(1+info)))
        if len({r["norad"] for r in parts})<2: continue
        offers.append(dict(time_s=float(tau), gain=float(cross*cross/information-np.log(information)),
            amplitude_reference_hz=300*cross/information, per_curve=parts))
    best=max(offers,key=lambda r:r["gain"]) if offers else None
    penalty=float(2*np.log(max(1,len(grid))*3))
    return dict(best=best,offers=offers,penalty=penalty,qualified=best is not None and best["gain"]>penalty,
        all_target_family_curves_excluded=True,candidate_norad=candidate,prior_sigma_hz=300,
        per_curve_constant_and_slope_projected_out_for_nomination=True)


def main(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    d=context(args); targets=select_targets(d); inv=inventory(d,targets)
    candidate=inv["screens"][0]["active"]["norad"]
    event=nominate_event(d,targets,candidate)
    report.write(out/"event_nomination.json",event)
    print("Independent event",event["best"],"penalty",event["penalty"],"qualified",event["qualified"],flush=True)
    variants=[("fast_smooth","fast",[])]
    if event["best"]:
        common=dict(time_s=event["best"]["time_s"],sigma_hz=300.,receiver=1)
        variants.extend((name,"original",[dict(common,kind=kind,**extra)]) for name,kind,extra in
            (("receiver_step","receiver_RF",{}),("high_band_step","band",dict(band=1))))
    trials={}
    for name,basis,events in variants:
        r,_=trial(d,targets,candidate,basis,events)
        trials[name]=r;report.write(out/(name+".json"),r)
        print(name,"valid",r["paired_valid"],[(a,[(t["gate"]["compatible"],t["gate"]["conditional_residual_gate"]["rms_hz"]) for t in v["targets"]],
              [g["component"] for g in v["gates"]["tracks"] if not g["compatible"]],v["event_amplitudes_hz"]) for a,v in r["arms"].items()],flush=True)
    figures(out,inv,trials)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",required=True,type=Path)
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--ch1",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    main(parser.parse_args())
