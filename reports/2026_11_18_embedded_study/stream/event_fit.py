"""Optimistic timing-only location with two-arm-consensus archive identities."""
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from sgp4.api import Satrec, SatrecArray

from check import MEMBERSHIP, OUTPUT, TRACK_ROOT, pass_center_time
from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)


WORKERS = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001/results")
NOMINAL = Path("/srv/bulk/leo/research/algo03-full-evaluation-20261030/cases")
REFERENCE = Path("/srv/bulk/leo/research/ds26-20261030/evaluation-site.json")
CENTER = np.array([37.906, -122.545])
ENU = ecef_to_enu_matrix(*CENTER)
OBSERVER = geodetic_to_ecef_km(*CENTER,0.)


def event_time(track):
    t = np.asarray(track["times"])
    y = np.asarray(track["values"])
    halves = [pass_center_time(t,y,k) for k in (0,1)]
    assert None not in halves and abs(halves[0]-halves[1]) <= 1
    shift = 10000. * (track["rf_hz"]/1.e9 - 11.5)
    shifted = [pass_center_time(t,y+shift,k) for k in (0,1)]
    assert max(abs(np.subtract(shifted,halves))) < 1e-7
    return float(np.mean(halves))


def model_time(position,velocity,times,east=0.,north=0.):
    observer = OBSERVER + east * ENU[0] + north * ENU[1]
    delta = position-observer
    sigma = np.linalg.norm(delta,axis=2)
    range_rate = np.einsum("ntj,ntj->nt",delta,velocity)/sigma
    acceleration = np.gradient(range_rate, times, axis=1)
    interest = np.flatnonzero((times >= 0) & (times <= 300))
    k = interest[np.argmax(acceleration[:,interest],axis=1)]
    row = np.arange(len(k))
    a, b, c = acceleration[row,k-1], acceleration[row,k], acceleration[row,k+1]
    centered = np.zeros(len(k))
    np.divide(.5*(a-c), a-2*b+c, out=centered,where=a-2*b+c < 0.)
    valid = (k > interest[0]+2) & (k < interest[-1]-2) & ((delta[row,k]@ENU[2])>0.) & (np.abs(centered)<1.)
    return np.where(valid,times[k]+centered,np.nan)


def dominant(track,arms):
    n = len(track["observation_ids"])
    labels = []
    for arm in ("c0","fitted_c"):
        votes = Counter(arms[arm]["owners"].get(oid) for oid in track["observation_ids"])
        number, support = votes.most_common(1)[0]
        if number is None or support < 0.8*n:
            return None
        labels.append(number)
    return labels[0] if labels[0] == labels[1] else None


def fit_case(case, event_indices):
    row = dict(case=case,events=len(event_indices),status="no archive owners or nominal elements")
    worker = WORKERS / (case+"-r0") / "baseline" / "worker-result.json"
    nominal = NOMINAL / case / "candidate-v2/recovery/snapshot/inference/SCAN/nominal_elements.json"
    if not worker.exists() or not nominal.exists():
        return row
    arms = json.loads(worker.read_bytes()).get("arms")
    if arms is None:
        return row
    track_data = json.loads((TRACK_ROOT / (case+".json")).read_bytes())
    elements = json.loads(nominal.read_bytes())
    measurements = defaultdict(list)
    for ix in event_indices:
        track = track_data["tracks"][ix]
        number = dominant(track,arms)
        if str(number) in elements:
            measurements[number].append(event_time(track))
    row["eligible_ids"] = len(measurements)
    row["eligible_events"] = sum(len(x) for x in measurements.values())
    if not measurements:
        row["status"] = "no consensus events"
        return row
    meta = track_data["metadata"]
    sats = []
    for number in measurements:
        elem = elements[str(number)]
        assert all(elem["provenance"][k]<=meta["causal_cutoff_utc_ns"] for k in ("element_epoch_utc_ns","collected_utc_ns"))
        sat = Satrec.twoline2rv(*elem["lines"])
        assert sat.satnum == number
        sats.append(sat)
    times = np.arange(-4,305,dtype=float)
    jd,fr = julian_day_from_utc_ns(meta["anchor_utc_ns"]+np.rint(times*1e9).astype(np.int64))
    errors, p, v = SatrecArray(sats).sgp4(jd,fr)
    p,v = teme_to_ecef(p,v,greenwich_mean_sidereal_time_rad(jd,fr))
    assert np.all(errors == 0)
    model = model_time(p,v,times)
    gradients = np.column_stack([(model_time(p,v,times,*(axis))-model_time(p,v,times,*(-np.array(axis))))/2
                                 for axis in ((1.,0.),(0.,1.))])
    y = np.array([np.median(x) for x in measurements.values()])
    delta_t = y-model
    valid = np.isfinite(model) & np.isfinite(gradients).all(axis=1)
    row["predicted_events"] = int(valid.sum())
    row["center_mismatch_s"] = np.abs(delta_t[valid]).tolist()
    row["time_gradient_s_km"] = np.linalg.norm(gradients[valid],axis=1).tolist()
    usable = valid & (abs(delta_t)<=8.)
    row["usable_ids"] = int(usable.sum())
    if usable.sum() < 3:
        row["status"] = "fewer than 3 coincident identities"
        return row
    H = gradients[usable]
    singular = np.linalg.svd(H,compute_uv=False)
    if singular[-1] < .1*singular[0] or singular[0]<1e-6:
        row["status"] = "near parallel gradients"
        return row
    fit = least_squares(lambda x: H@x-delta_t[usable],np.zeros(2),jac=lambda x:H.copy(),
                        bounds=(-12.5,12.5),loss="huber",f_scale=1.)
    assert fit.success
    east,north = fit.x
    row.update(status="fit", xy_km=fit.x.tolist(),latlon=[CENTER[0]+north/111., CENTER[1]+east/(111.32*np.cos(np.deg2rad(CENTER[0])))],
               boundary=bool(np.any(abs(fit.x)>12.49)),
               timing_rms_s=float(np.sqrt(np.mean((H@fit.x-delta_t[usable])**2))))
    return row


def surface_error(latlon,ref):
    a,b = np.deg2rad(latlon), np.deg2rad(ref)
    dlat, dlon = a-b
    h = np.sin(dlat/2)**2 + np.cos(a[0])*np.cos(b[0])*np.sin(dlon/2)**2
    return float(2*6371.0088*np.arcsin(np.sqrt(h)))


def stats(x):
    return dict(zip(("n","min","median","p95","max"),[len(x),*np.percentile(x,[0,50,95,100]).tolist()],strict=True)) if x else None


def main():
    members = json.loads(MEMBERSHIP.read_bytes())["dataset_labels"]
    stable = {r["case"]:r["stable_track_indexes"] for r in json.loads((OUTPUT/"checks.json").read_bytes())["cases"] if r["available"]}
    results = [fit_case(case,stable[case]) if case in stable else dict(case=case,status="missing native input",events=0) for case in members]
    truth = json.loads(REFERENCE.read_bytes())
    ref = [truth["latitude_deg"],truth["longitude_deg"]]
    for row in results:
        if row["status"]=="fit":
            row["error_km"] = surface_error(row["latlon"],ref)
    fits = [r for r in results if r["status"]=="fit"]
    summary = dict(
        selection="Requires archived, 80%-supported identical satellite ownership in both v5 arms, held fixed for evaluation. Offline tracks. Initial 48h causal nominal TLEs. Fit 2D horizontal displacement by equal-satellite Huber timing residuals, +/-12.5 km, after an 8 s center residual gate; at least 3 unique visible interior events and nonparallel geometry.",
        calibration="Time of steepest negative slope cancels every constant and affine shift per lane. Numerically rechecked c=10 kHz/GHz on every accepted measured event against c=0, error <1e-7 s; free c is unidentifiable.",
        statuses=dict(Counter(r["status"] for r in results)), counts={k:sum(r.get(k,0) for r in results) for k in ("events","eligible_events","eligible_ids","predicted_events","usable_ids")},
        time_gradient_s_km=stats([x for r in results for x in r.get("time_gradient_s_km",[])]),
        center_mismatch_s=stats([x for r in results for x in r.get("center_mismatch_s",[])]),
        horizontal_error_km=stats([r["error_km"] for r in fits]), boundary=sum(r["boundary"] for r in fits),
        timing_rms_s=stats([r["timing_rms_s"] for r in fits]))
    (OUTPUT/"event_results.json").write_text(json.dumps(dict(summary=summary,cases=results),allow_nan=False,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
