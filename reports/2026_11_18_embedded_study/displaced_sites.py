"""Matched synthetic displacement controls. Fresh SGP4 creates signals at four sites."""

import json

import numpy as np

import cold_replay as cold


def generate(case, bank, receipt, graph, xy):
    rng = np.random.default_rng(88061 + int(case[-4:]))
    timesrc = [graph["tracks"][i] for i in graph["curved_indices"]]
    rng.shuffle(timesrc)
    lookup = {s.satnum:s for s in cold.parse_element_sets(
        next((cold.INPUT/case/"tle").rglob(receipt["snapshot"])).read_text()
    ).satellites}
    new = dict(tracks=[],curved_indices=[])
    phases = {int(n):rng.normal(0,.7) for n in bank["ids"]}
    common = rng.uniform(-12000,12000,4)
    drift = rng.uniform(-2,2,4)
    for template in timesrc:
        t = np.array(template["times"])
        if len(t)<12 or np.ptp(t)<25:
            continue
        ups = cold.interpolate(bank["up"],np.array([t[0],t[len(t)//2],t[-1]]),bank)
        plausible = np.flatnonzero(ups.min(axis=1)>np.sin(np.deg2rad(16)))
        if not len(plausible):
            continue
        sat = int(bank["ids"][rng.choice(plausible)])
        g = 2*(template["receiver"]-1)+int(template["channel"]>4)
        ratio = template["rf_hz"]/cold.CARRIER
        _,p,v = cold.state([lookup[sat]],graph["metadata"]["anchor_utc_ns"],t+phases[sat])
        freq = cold.projection(p,v,xy)[0][0] * ratio
        y = (freq + common[g] + drift[g]*(t-150) + 1400*(template["rf_hz"]/1e9-11.5)
             + rng.normal(0,90,len(t)))
        # Known artificial outliers share an arbitrary extra offset in one out of eight tracks.
        if len(new["tracks"]) % 8 == 7:
            y += 7000.
        y -= cold.PERIOD*np.rint(y[0]/cold.PERIOD)
        track = dict(receiver=template["receiver"],channel=template["channel"],
                     rf_hz=template["rf_hz"],times=t,values=y)
        xc = t - t.mean()
        detrended = y-y.mean() - xc*(xc@(y-y.mean()))/(xc@xc)
        if np.sqrt(np.mean(detrended**2)) >= 250:
            new["curved_indices"].append(len(new["tracks"]))
        new["tracks"].append(track)
        if len(new["tracks"])==40:
            break
    return new


def main():
    fixtures = []
    for case in cold.panel()[::8]:
        graph = cold.read(cold.GRAPHS/f"{case}.json")
        bank,receipt = cold.build_bank(case,graph["metadata"],check_approximation=False)
        for xy in ((-7.,-7.),(-7.,7.),(7.,-7.),(7.,7.)):
            simulated = generate(case,bank,receipt,graph,xy)
            d = cold.descriptors(simulated,bank)
            if d is None:
                fixtures.append(dict(case=case,true_xy=xy,status="insufficient"))
                continue
            bias = cold.bias_vote(d)
            _,start,winners,loss = cold.grid_vote(d,bias)
            selected = np.flatnonzero(loss<12.)
            arms = {}
            for arm in ("c0","fitted_c"):
                fit = cold.solve(d,selected,winners,bias,start,fitted_c=arm=="fitted_c")
                if fit["status"]=="estimate":
                    fit["local_error_km"] = float(np.linalg.norm(np.array(xy)-fit["xy"]))
                    fit["correct_quadrant"] = bool(np.all(np.sign(xy)==np.sign(fit["xy"])))
                arms[arm] = fit
            fixtures.append(dict(case=case,true_xy=xy,curved=len(d["ti"]),arms=arms))
    (cold.ROOT/"displaced-sites.json").write_text(json.dumps(fixtures,allow_nan=False))


if __name__=="__main__":
    main()
