"""Inspect previous-only priors, satellite-ID turnover and a zero-radio learned predictor."""
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np


CAMPAIGN = Path("/srv/bulk/leo-dev/accuracy-repair-20261115/ds26-four-configs-twice-001/results")
DS26 = Path("/srv/bulk/leo/research/ds26-20261030")
DS29_REFERENCES = Path("/srv/bulk/leo-dev/ds29-20261113/snapshot/evaluation-references.json")
ARMS = ("c0", "fitted_c")
ANCHOR_STRIDE = 4
HISTORY_LENGTH = 4


def load(path):
    return json.loads(path.read_bytes())


def haversine(first, second):
    lat, lon = np.deg2rad(first)
    rlat, rlon = np.deg2rad(second)
    a = math.sin((lat - rlat) / 2) ** 2 + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
    return 12742.0176 * math.asin(math.sqrt(min(a, 1.0)))


def distribution(values):
    arr = np.asarray(values)
    return dict(n=len(arr), mean=float(np.mean(arr)), median=float(np.median(arr)),
                p95=float(np.percentile(arr, 95)), max=float(np.max(arr))) if len(arr) else dict(n=0)


@dataclass
class Scan:
    name: str
    start: float
    index: int
    edge: str
    status: str
    available_after: float | None
    pos: dict
    owners: dict
    residual_rms_hz: dict
    worker_s: float | None


def scan_series():
    members = load(DS26 / "fast-only-evaluation-membership.json")["members"]
    report = load(CAMPAIGN / "repeat-comparison.json")
    ledger = {r["case"]: r["status"] for r in report["coverage"]
              if r["repetition"] == 0 and r["role"] == "baseline"}
    result = []
    for index, member in enumerate(sorted(members, key=lambda m: m["captured_utc_ns"])):
        name = member["dataset_label"]
        folder = CAMPAIGN / (name + "-r0")
        start = member["captured_utc_ns"] / 1e9
        status = ledger[name]
        p, owners, residual = {}, {}, {}
        ready = worker_s = None
        if status == "complete":
            timing = load(folder / "baseline-execution.json")
            worker_s = timing["process"]["wall_seconds"]
            # Capture starts ~5-min observations. This eligibility model omits unmeasured
            # IQ-to-GLRT delay; the chronology below is an explicitly modeled schedule.
            ready = start + 300 + worker_s
            arms = timing["worker"]["arms"]
            for arm in ARMS:
                p[arm] = arms[arm]["endpoint_latlon"]
                owners[arm] = Counter(arms[arm]["owners"].values())
                residual[arm] = arms[arm]["residual_rms_hz"]
                assert sum(owners[arm].values()) == arms[arm]["associated_points"]
                assert len(owners[arm]) == arms[arm]["satellites"]
        result.append(Scan(name, start, index, member["recording_id"].split("-")[-1], status,
                           ready, p, owners, residual, worker_s))
    assert len(result) == len(ledger) == len({r.name for r in result}) == 159
    return result


def historic_positions(scans, anchor_phase=0):
    rows = []
    for current in scans:
        earlier = [s for s in scans[:current.index]
                   if s.status == "complete" and s.available_after <= current.start]
        anchors = [s for s in earlier if s.index % ANCHOR_STRIDE == anchor_phase]
        row = {"case": current.name, "slot": current.index, "status": current.status,
               "anchor_due": current.index % ANCHOR_STRIDE == anchor_phase, "prediction": {},
               "latest_source": earlier[-1].name if earlier else None,
               "anchor_sources": [s.name for s in anchors[-HISTORY_LENGTH:]],
               "latest_anchor_age_hours": (current.start-anchors[-1].start)/3600 if anchors else None,
               "oldest_used_anchor_age_hours": (current.start-anchors[-HISTORY_LENGTH:][0].start)/3600 if anchors else None}
        if earlier:
            for arm in ARMS:
                row["prediction"][arm] = {
                    "last_only": earlier[-1].pos[arm],
                    "prior_four_mean": np.mean([s.pos[arm] for s in earlier[-HISTORY_LENGTH:]], axis=0).tolist(),
                }
                if anchors:
                    row["prediction"][arm]["anchor_only_mean"] = np.mean(
                        [s.pos[arm] for s in anchors[-HISTORY_LENGTH:]], axis=0).tolist()
        rows.append(row)
    return rows


def overlap_rows(scans):
    pairs = []
    for current in scans:
        if current.status != "complete":
            continue
        previous = [s for s in scans[:current.index] if s.status == "complete" and s.available_after <= current.start]
        if not previous:
            continue
        for arm in ARMS:
            current_ids = current.owners[arm]
            for name, sources in (("last_available", previous[-1:]),
                                  ("last_four_union", previous[-HISTORY_LENGTH:]),
                                  ("last_same_edge", [s for s in previous if s.edge == current.edge][-1:])):
                if not sources:
                    continue
                ids = set().union(*(s.owners[arm] for s in sources))
                common = ids.intersection(current_ids)
                hits = sum(current_ids[n] for n in common)
                pairs.append(dict(case=current.name, arm=arm, history=name,
                                  last_source=sources[-1].name, age_minutes=(current.start-sources[-1].start)/60,
                                  gap_from_last_eligible_scans=current.index-sources[-1].index,
                                  pool=len(ids), current=len(current_ids), overlap=len(common),
                                  hits=hits, total=sum(current_ids.values())))
    return pairs


def summarize(scans, forecasts, overlaps):
    site = load(DS26 / "evaluation-site.json")
    target = (site["latitude_deg"], site["longitude_deg"])
    published = load(CAMPAIGN / "repeat-comparison.json")["repeat_measurements"]
    reference_errors = {r["case"]: r.get("arms", {}) for r in published if r["role"] == "baseline"}
    prediction_summary = {}
    for arm in ARMS:
        arm_summary = {}
        for method in ("last_only", "prior_four_mean", "anchor_only_mean"):
            rows = [(s, r) for s, r in zip(scans, forecasts, strict=True) if method in r["prediction"].get(arm, {})]
            matches = [(s, r) for s, r in rows if s.status == "complete"]
            separations = [haversine(s.pos[arm], r["prediction"][arm][method]) for s, r in matches]
            arm_summary[method] = dict(
                all_forecasts_km=distribution([haversine(r["prediction"][arm][method], target) for _, r in rows]),
                matched_forecasts_km=distribution([haversine(r["prediction"][arm][method], target) for _, r in matches]),
                matched_current_v5_km=distribution([haversine(s.pos[arm], target) for s, _ in matches]),
                current_v5_training_rms_hz=distribution([s.residual_rms_hz[arm] for s, _ in matches]),
                median_displacement_from_new_v5_km=distribution(separations)["median"],
                n_current_v5_within_warm_search_radius_km={
                    str(radius):sum(value <= radius for value in separations) for radius in (1, 2, 5)
                },
                current_rf_in_forecast=False,
            )
        prediction_summary[arm] = arm_summary
    agreement = []
    for s in scans:
        if s.status != "complete":
            continue
        for arm in ARMS:
            if arm in reference_errors[s.name]:
                pair = reference_errors[s.name][arm]["gps_error_km"]
                if "first" in pair:
                    agreement.append(abs(haversine(s.pos[arm], target) - pair["first"]))
    assert agreement and max(agreement) < 1e-8
    overlap_summary = {}
    for arm in ARMS:
        for source in ("last_available", "last_four_union", "last_same_edge"):
            rows = [r for r in overlaps if r["arm"] == arm and r["history"] == source]
            overlap_summary[arm + "/" + source] = dict(
                n=len(rows), pool=distribution([r["pool"] for r in rows]),
                current=distribution([r["current"] for r in rows]),
                overlap_ids=distribution([r["overlap"] for r in rows]),
                total_ids=sum(r["current"] for r in rows), shared_ids=sum(r["overlap"] for r in rows),
                hit_points=sum(r["hits"] for r in rows), total_points=sum(r["total"] for r in rows),
                no_common_ids=sum(r["overlap"] == 0 for r in rows),
                three_or_more_common_ids=sum(r["overlap"] >= 3 for r in rows),
                interval_minutes=distribution([r["age_minutes"] for r in rows]),
            )
    ds29 = load(DS29_REFERENCES)
    sites29 = Counter((r["latitude_deg"], r["longitude_deg"]) for r in ds29.values())
    unit_km = haversine(target, next(iter(sites29)))
    phase_control = {}
    for phase in range(ANCHOR_STRIDE):
        records = historic_positions(scans, phase)
        positions = [r for r in records if r["anchor_sources"] and r["status"] == "complete"]
        phase_control[str(phase)] = dict(
            eligible_successes=len(positions),
            scheduled_anchors=dict(Counter(s.status for s in scans if s.index % ANCHOR_STRIDE == phase)),
            forecast_km={arm: distribution([haversine(row["prediction"][arm]["anchor_only_mean"], target)
                                           for row in positions]) for arm in ARMS},
            latest_anchor_age_hours=distribution([r["latest_anchor_age_hours"] for r in records if r["anchor_sources"]]),
            oldest_anchor_age_hours=distribution([r["oldest_used_anchor_age_hours"] for r in records if r["anchor_sources"]]),
        )
    return dict(
        primary_scans=159, baseline_repeat="r0", r0_status=dict(Counter(s.status for s in scans)),
        source_model="Earlier successful v5 endpoints available following 300-second capture plus that worker's measured wall time. Front-end/queue latency unmeasured.",
        same_site_multiple_visits=True, primary_outputs_checked_against_published_results=len(agreement),
        primary_output_max_abs_difference_km=max(agreement), summary_km=prediction_summary,
        scan_start_spacing_min=distribution(np.diff([s.start for s in scans]) / 60),
        prior_position_only_has_RF_fit=False, history_length=HISTORY_LENGTH, anchor_stride=ANCHOR_STRIDE,
        scheduled_anchors=dict(Counter(s.status for s in scans if s.index % ANCHOR_STRIDE == 0)),
        overlap=overlap_summary, alternate_anchor_phase=phase_control,
        direct_position_learning_control=dict(
            training_method="chronological first DS26 reference only; use its coordinate for every subsequent prediction",
            unique_train_locations=1, n_DS26_holdout=len(scans)-1, DS26_test_error_m=0.0,
            n_DS29_holdout=len(ds29), unique_DS29_locations=len(sites29),
            DS29_same_constant_error_m=1000*unit_km if len(sites29)==1 else None,
            DS29_reference="operator-supplied roof", uses_radio=False),
    )


if __name__ == "__main__":
    scans = scan_series()
    forecasts = historic_positions(scans)
    overlaps = overlap_rows(scans)
    summary = summarize(scans, forecasts, overlaps)
    path = Path(__file__).resolve().parent
    (path / "results.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    (path / "per_scan.json").write_text(json.dumps(dict(forecasts=forecasts, id_checks=overlaps), separators=(",", ":")) + "\n")
