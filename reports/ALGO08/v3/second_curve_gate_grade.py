"""Grade captured curve gates on the same signed mixed packet, without inference."""

from collections import Counter
from hashlib import sha256
from math import fsum, sqrt
from statistics import fmean
from pathlib import Path
import argparse
import json

from pre_screen_owner_readout import CASES, HERE, ROOT, RELEASE, checked, document, owner_map
from second_curve_gate_trial import snapshot


RATE = 10_000_000
LIMITS = {"mean_z":3., "slope_z":3., "quadratic_bic_gain":10., "maximum_step_z":4.}
RUNS = ("DS30-0220","DS30-0086")
GATE_SOURCES = {
    "src/leo/analysis/research/polynomial_satellite_diagnostics.py":
        "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5",
    "src/leo/analysis/localization_v3/acceptance.py":
        "d4a3c3d8331c9e24d678d3c271139fbb8da62356b66274f93042774c89196353",
}


def row_headroom(row, times):
    cond = row["conditional"]
    diag = cond["diagnostics"]
    points = len(times)
    mean_time = fmean(times)
    variance_time = fsum((t-mean_time)**2 for t in times)
    std = sqrt(max(0.,points/(points-1)*(cond["rms_hz"]**2-cond["mean_hz"]**2)))
    sigma = max(std,75.)
    scale = sigma/sqrt(variance_time)
    limits = dict(LIMITS,lag1_acf=4/sqrt(points))
    conditional_failed = [key for key,limit in limits.items()
                          if (abs(diag[key]) if key=="lag1_acf" else diag[key])>limit]
    if cond["rms_hz"]>450:
        conditional_failed.append("rms_hz")
    if cond["compatible"]==bool(conditional_failed):
        raise ValueError("The exact conditional gate is inconsistent with its reported values")
    return dict(span_s=max(times)-min(times),conditional_sigma_from_moments_hz=sigma,
                normalized_slope_scale_hz_per_s=scale,
                absolute_slope_from_z_hz_per_s=diag["slope_z"]*scale,
                signed_slope_hz_per_s=None,conditional_failed=conditional_failed)


def direct(path):
    return json.loads(path.read_bytes())


def next_official(event, exit_ns):
    path = ROOT.parent/event["event"]
    following = next(p for p in sorted(path.parent.glob("*.json"))
                     if int(p.name.split("-")[0])>event["unix_ns"])
    latency = (int(following.name.split("-")[0])-exit_ns)/1e9
    if latency <= 0:
        raise ValueError("Official next poll reached the stage-only lease")
    return dict(event=str(following.relative_to(ROOT.parent)),state=direct(following)["state"],
                receipt_sha256=sha256(following.read_bytes()).hexdigest(),seconds_after_exit=latency)


def grade(case):
    tail = case[-4:]
    base = Path(f"/dev/shm/leo-v3-second-gate-{tail}-run01")
    run = base/"run"
    clock = direct(run/"clock.json")
    stage = direct(run/"stage-result.json")
    ready_path = Path(f"/dev/shm/leo-v3-second-gate-{tail}-ready01.json")
    started = direct(base/"watch-start.json")
    ready = document(ready_path,started["ready_sha256"])
    pin = CASES[case]
    if (clock["exit"] or not clock["stage_started"] or clock["wall_s"]>=18
            or stage["case"]!=case or stage["native_sha256"]!="sha256:"+pin["native"]
            or any(stage[key] for key in ("acquisition","finishing_fits","rendered"))):
        raise ValueError("Only the completed attested stage may be graded")
    trace = {label:document(run/f"{label}.json",digest) for label,digest in stage["masks"].items()}
    if {label:snapshot(rows) for label,rows in trace.items()}!=ready["expected_stage_masks"]:
        raise ValueError("The emitted masks differ from the preflight")
    original = ROOT/case/"successor/attempt-000001/publication"
    native_path, = (original/"fast-scan-automatic-work").glob("*/detections.json")
    native = document(native_path,pin["native"])
    source = native["source"]
    if source["sample_rate_hz"]!=RATE or source["probe_ms"]!=20:
        raise ValueError("Unexpected original hardware time basis")
    anchor = native["clock_anchor"]["sample_counter"]
    sample = {}
    for probe in source["probes"]:
        counter = probe["valid_start_counter"]
        radio = probe["receiver_id"]
        identity = "sha256:"+sha256(f'{source["session_id"]}:{radio}:{counter}'.encode()).hexdigest()
        if identity in sample:
            raise ValueError("Duplicate original hardware opportunity")
        sample[identity] = (counter,radio,probe["channel"],probe["actual_rf_hz"])
    named = document(HERE/"measurements"/f"field-receiver-solver-cross-{tail}.json.gz",pin["crossover"])["score"]
    current = document(original/"exact-named-raw-witness.json",pin["charted"])["evidence"]
    missing = {}
    for arm in ("c0","fitted_c"):
        tracked = owner_map(current["owner_rows"][arm],current["owner_maps"][arm])
        installed = owner_map(named["new_owners"][arm],named["new_owner_maps"][arm])
        missing[arm] = {key:value for key,value in installed.items() if key not in tracked}
    failures = []
    healthy_radios = Counter()
    for row in trace["after_salvage"]["tracks"]:
        points = [sample[key] for key in row["observation_ids"]]
        lane = {x[1:] for x in points}
        if len(lane)!=1 or any(b[0]<=a[0] for a,b in zip(points,points[1:])):
            raise ValueError("Gate rows differ from the original order or hardware stream")
        slot, = lane
        if row["compatible"]:
            healthy_radios[str(slot[0])] += row["points"]
            continue
        fields = row_headroom(row,[(p[0]-anchor)/RATE+.01 for p in points])
        losses = {arm:sum(book.get(key)==(row["norad"],row["role"]) for key in row["observation_ids"])
                  for arm,book in missing.items()}
        failures.append(dict(component=row["component"],points=row["points"],norad=row["norad"],
                             radio=slot[0], channel=slot[1], rf_hz=slot[2],first_counter=points[0][0],
                             last_counter=points[-1][0],installed_only=losses,**fields,
                             conditional_abs_slope_z=row["conditional"]["diagnostics"]["slope_z"],
                             tests_failed=[name for name,passes in row["actual_tests"].items() if not passes],
                             family_support_groups=row["family_support_groups"]))
    event = direct(base/"gate.json")
    return dict(case=case,clock=clock,stage=stage,ready=ready,watch_started=started,watch_gate=event,
                official_followup=next_official(event,clock["terminated_unix_ns"]),gate_source_sha256=GATE_SOURCES,
                watch_finished=direct(base/"watch-end.json"),masks=trace,signed_slope_available=False,
                rejected_second=failures,surviving_points_by_native_radio=healthy_radios)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases",choices=RUNS,nargs="+")
    for name,pin in GATE_SOURCES.items():
        checked(RELEASE/name,pin)
    results = {case:grade(case) for case in parser.parse_args().cases}
    print(json.dumps(results,indent=2,sort_keys=True,allow_nan=False))
