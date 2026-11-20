"""Bounded stationary forecasts from full historical anchor scans."""

from collections import Counter, deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import median
import sys
from time import perf_counter


OUTPUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUTPUT.parent))
from bench import CASES, latlon


ARMS = ("c0", "fitted_c")
MEMBERSHIP = Path("/srv/bulk/leo/research/ds26-20261030/fast-only-evaluation-membership.json")
NS = 10**9
STRIDE = 16
CAPTURE_ENVELOPE_S = 360
FRONTEND_ALLOWANCE_S = 60
STALE_S = 24 * 3600
HISTORY_S = 48 * 3600
HISTORY_LIMIT = 4


@dataclass(frozen=True)
class Scan:
    case: str
    start_ns: int
    slot: int


@dataclass(frozen=True)
class Fix:
    scan: Scan
    available_ns: int
    xy: tuple[float, float]


class Stationary:
    """The foreground state accepts only completed position fixes and a clock."""

    def __init__(self):
        self.fixes = deque(maxlen=HISTORY_LIMIT)
        self.latest = None
        self.resets = 0

    def _expire(self, now_ns):
        if self.fixes and now_ns - self.latest.scan.start_ns > STALE_S * NS:
            self.fixes.clear()
            self.resets += 1
        while self.fixes and now_ns - self.fixes[0].scan.start_ns > HISTORY_S * NS:
            self.fixes.popleft()

    def offer(self, fix, cutoff_ns):
        if not fix.scan.start_ns < fix.available_ns < cutoff_ns:
            return False
        if self.latest and fix.scan.start_ns <= self.latest.scan.start_ns:
            return False
        self._expire(fix.available_ns)
        self.latest = fix
        self.fixes.append(fix)
        return True

    def forecast(self, cutoff_ns):
        self._expire(cutoff_ns)
        latest_age = (cutoff_ns - self.latest.scan.start_ns) / NS if self.latest else None
        receipt = dict(
            kind="forecast",
            anchor_count=len(self.fixes),
            anchor_cases=[fix.scan.case for fix in self.fixes],
            latest_anchor_age_s=latest_age,
            oldest_used_anchor_age_s=(cutoff_ns - self.fixes[0].scan.start_ns) / NS if self.fixes else None,
            latest_anchor_available_ns=self.latest.available_ns if self.latest else None,
            stale_resets=self.resets,
            rms_hz=None,
        )
        if not self.fixes:
            reason = "stale_anchor" if self.latest else "no_available_anchor"
            return dict(status="abstain", reason=reason, last_anchor_control=None, **receipt)
        east, north = zip(*(fix.xy for fix in self.fixes), strict=True)
        return dict(
            status="estimate",
            latlon=latlon((median(east), median(north))),
            last_anchor_control=dict(kind="forecast", latlon=latlon(self.latest.xy), rms_hz=None),
            **receipt,
        )


def scan_schedule():
    members = json.loads(MEMBERSHIP.read_bytes())["members"]
    ordered = sorted(members, key=lambda row: (row["captured_utc_ns"], row["dataset_label"]))
    return {
        row["dataset_label"]: Scan(row["dataset_label"], row["captured_utc_ns"], slot)
        for slot, row in enumerate(ordered)
    }


def solve_anchor(scan):
    """Run the shared cold estimator with its one common proposal and two fits."""
    import numpy as np

    import cold_replay as cold

    start = perf_counter()
    graph_bytes = None
    end_ns = None
    capture_s = None
    bank_receipt = None
    failure = None
    tracks = None
    selected_count = None
    arms = {}
    try:
        data = (cold.GRAPHS / f"{scan.case}.json").read_bytes()
        graph_bytes = len(data)
        doc = json.loads(data)
        meta = doc["metadata"]
        duration_s = meta["duration_s"]
        capture_end_ns = max(scan.start_ns, meta["anchor_utc_ns"]) + math.ceil(duration_s * NS)
        if not 0 < duration_s or capture_end_ns - scan.start_ns > CAPTURE_ENVELOPE_S * NS:
            raise ValueError("capture outside scheduled envelope")
        capture_s = duration_s
        end_ns = capture_end_ns
        bank, bank_receipt = cold.build_bank(scan.case, meta, check_approximation=False)
        descriptors = cold.descriptors(doc, bank)
        if descriptors is None:
            failure = "no_curved_tracks"
        else:
            tracks = len(descriptors["ti"])
            bias = cold.bias_vote(descriptors)
            _, position, winners, cost = cold.grid_vote(descriptors, bias)
            selected = np.flatnonzero(cost < 12.)
            selected_count = int(len(selected))
    except (IndexError, KeyError, OSError, ValueError, OverflowError, np.linalg.LinAlgError) as exc:
        failure = f"{type(exc).__name__}: {exc}"
    common_wall_s = perf_counter() - start
    if failure is None:
        for arm in ARMS:
            fit_start = perf_counter()
            try:
                fit = cold.solve(descriptors, selected, winners, bias, position, fitted_c=arm == "fitted_c")
            except (ValueError, np.linalg.LinAlgError) as exc:
                fit = dict(status="anchor_unavailable", reason=f"{type(exc).__name__}: {exc}")
            fit["fit_wall_s"] = perf_counter() - fit_start
            arms[arm] = fit
    wall_s = perf_counter() - start
    for arm in ARMS:
        arms.setdefault(arm, dict(status="anchor_unavailable", reason=failure, fit_wall_s=0.))
        arms[arm]["standalone_wall_s"] = common_wall_s + arms[arm]["fit_wall_s"]
    envelope_end_ns = scan.start_ns + CAPTURE_ENVELOPE_S * NS
    # Both arms receive the same conservative paired release time. Even if graph
    # construction were instantaneous, receipt precedes consumption strictly.
    ready_after_capture_ns = (end_ns if end_ns is not None else envelope_end_ns) + FRONTEND_ALLOWANCE_S * NS
    available_ns = max(envelope_end_ns, ready_after_capture_ns) + math.ceil(wall_s * NS)
    return dict(
        case=scan.case,
        slot=scan.slot,
        start_ns=scan.start_ns,
        modeled_availability_ns=available_ns,
        capture_s=capture_s,
        wall_s=wall_s,
        common_wall_s=common_wall_s,
        graph_bytes=graph_bytes,
        bank=bank_receipt,
        considered_tracks=tracks,
        selected_tracks_both_arms=selected_count,
        arms=arms,
    )


def replay(queries, scheduled, anchor_loader):
    """Materialize only prior complete captures and gate fixes again by release."""
    states = {arm: Stationary() for arm in ARMS}
    scheduled = deque(scheduled)
    pending = []
    receipts = []
    cases = []
    for query in queries:
        anchor_cost_s = 0.
        newly_attempted = []
        while scheduled and scheduled[0].start_ns + CAPTURE_ENVELOPE_S * NS < query.start_ns:
            scan = scheduled.popleft()
            receipt = anchor_loader(scan)
            receipts.append(receipt)
            pending.append((scan, receipt))
            newly_attempted.append(scan.case)
            anchor_cost_s += receipt["wall_s"]
        foreground_start = perf_counter()
        released = []
        in_flight = []
        for scan, receipt in pending:
            ready_ns = receipt["modeled_availability_ns"]
            if ready_ns < query.start_ns:
                released.append((ready_ns, scan, receipt))
            else:
                in_flight.append((scan, receipt))
        pending = in_flight
        for ready_ns, scan, receipt in sorted(released, key=lambda row: (row[0], row[1].slot)):
            for arm, state in states.items():
                fit = receipt["arms"][arm]
                if fit["status"] == "estimate":
                    state.offer(Fix(scan, ready_ns, tuple(fit["xy"])), query.start_ns)
        arms = {}
        for arm, state in states.items():
            arm_start = perf_counter()
            forecast = state.forecast(query.start_ns)
            forecast["forecast_wall_s"] = perf_counter() - arm_start
            arms[arm] = forecast
        cases.append(dict(
            case=query.case,
            query_utc_ns=query.start_ns,
            wall_s=perf_counter() - foreground_start,
            newly_attempted_anchors=newly_attempted,
            newly_released_jobs=[scan.case for _, scan, _ in released],
            pending_jobs=[scan.case for scan, _ in pending],
            anchor_job_wall_s_since_prior_query=anchor_cost_s,
            current_rf_capture_s=0,
            current_rf_bytes_read=0,
            arms=arms,
        ))
    return cases, receipts, [scan.case for scan in scheduled]


def cost_receipt(cases, jobs):
    same_anchor_fits = [job for job in jobs if all(job["arms"][arm]["status"] == "estimate" for arm in ARMS)]
    paired_delta = [job["arms"]["fitted_c"]["rms_hz"] - job["arms"]["c0"]["rms_hz"] for job in same_anchor_fits]
    capture = [job["capture_s"] for job in jobs if job["capture_s"] is not None]
    return dict(
        attempted_anchor_jobs=len(jobs),
        anchor_capture_s_total=sum(capture),
        attempted_anchors_with_unknown_capture_s=len(jobs) - len(capture),
        archived_graph_bytes_read=sum(job["graph_bytes"] or 0 for job in jobs),
        paired_anchor_wall_s=sum(job["wall_s"] for job in jobs),
        foreground_pair_wall_s=sum(case["wall_s"] for case in cases),
        paired_anchor_rms=dict(
            samples=len(paired_delta),
            median_fitted_minus_c0_hz=median(paired_delta) if paired_delta else None,
            fitted_lower_count=sum(delta < 0 for delta in paired_delta),
        ),
        arms={arm: dict(
            anchor_status_counts=dict(Counter(job["arms"][arm]["status"] for job in jobs)),
            forecast_status_counts=dict(Counter(case["arms"][arm]["status"] for case in cases)),
            forecast_outage_reasons=dict(Counter(
                case["arms"][arm]["reason"] for case in cases if case["arms"][arm]["status"] == "abstain"
            )),
            standalone_anchor_wall_s=sum(job["arms"][arm]["standalone_wall_s"] for job in jobs),
            amortized_standalone_anchor_wall_s_per_query=(
                sum(job["arms"][arm]["standalone_wall_s"] for job in jobs) / len(cases)
            ),
            foreground_forecast_wall_s=sum(case["arms"][arm]["forecast_wall_s"] for case in cases),
        ) for arm in ARMS},
    )


def main():
    from test_stationary import check

    checks = check()
    scans = scan_schedule()
    queries = sorted((scans[case] for case in CASES), key=lambda scan: scan.start_ns)
    scheduled = [scan for scan in scans.values() if scan.slot % STRIDE == 0 and scan.start_ns < queries[-1].start_ns
                 and scan.case not in CASES]
    cases, jobs, not_read = replay(queries, scheduled, solve_anchor)
    jobs_by_case = {job["case"]: job for job in jobs}
    assert set(jobs_by_case).isdisjoint(CASES)
    for case in cases:
        for forecast in case["arms"].values():
            for anchor in forecast["anchor_cases"]:
                job = jobs_by_case[anchor]
                assert job["start_ns"] < job["modeled_availability_ns"] < case["query_utc_ns"]
    result = dict(
        method="Stationary four-anchor coordinate median",
        timing_scope="Foreground releases of finished fixes and both forecasts. Historical anchor graph I/O, TLE "
                     "propagation, association and fit have separate measured costs. No IQ or detector timing.",
        cases=cases,
        checks=dict(
            configuration=dict(stride=STRIDE, history_limit=HISTORY_LIMIT, staleness_s=STALE_S,
                               anchor_retention_s=HISTORY_S, front_end_allowance_s=FRONTEND_ALLOWANCE_S,
                               capture_envelope_s=CAPTURE_ENVELOPE_S),
            synthetic=checks,
            costs=cost_receipt(cases, jobs),
            historical_anchor_jobs=jobs,
            scheduled_jobs_not_read_by_last_query=not_read,
        ),
    )
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    # Keep the executable and the component-owned checks on the same implementation.
    sys.modules.setdefault("stationary", sys.modules[__name__])
    main()
