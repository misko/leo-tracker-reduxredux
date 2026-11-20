"""Deterministic timing, outage and relocation checks without archived input."""

import json

from stationary import ARMS, NS, STALE_S, Fix, Scan, Stationary, latlon, replay


def check():
    def seconds(value):
        return value * NS

    def fix(name, start, ready, east, north=0):
        return Fix(Scan(name, seconds(start), start), seconds(ready), (east, north))

    stationary = Stationary()
    assert stationary.forecast(seconds(1))["reason"] == "no_available_anchor"
    for row in (fix("A", 10, 11, 0), fix("B", 20, 21, 0), fix("outlier", 30, 31, 10)):
        assert stationary.offer(row, seconds(40))
    forecast = stationary.forecast(seconds(40))
    assert forecast["latlon"] == latlon((0, 0))
    assert forecast["last_anchor_control"]["latlon"] == latlon((10, 0))
    assert forecast["anchor_count"] == 3

    # A relocation at t=40 provides no input to this filter until another anchor.
    # Even the first relocated anchor is outvoted by the older history.
    relocated = fix("relocated", 50, 51, -10)
    assert stationary.offer(relocated, seconds(60))
    after_relocated_fix = stationary.forecast(seconds(60))
    assert after_relocated_fix["latlon"] == latlon((0, 0))
    assert after_relocated_fix["last_anchor_control"]["latlon"] == latlon((-10, 0))
    assert stationary.forecast(seconds(50 + STALE_S))["status"] == "estimate"
    stale = stationary.forecast(seconds(51 + STALE_S))
    assert stale["status"] == "abstain" and stale["reason"] == "stale_anchor"
    assert stale["anchor_count"] == 0 and stale["stale_resets"] == 1
    refreshed = fix("reinitialized", STALE_S + 60, STALE_S + 61, -10)
    assert stationary.offer(refreshed, seconds(STALE_S + 62))
    reset = stationary.forecast(seconds(STALE_S + 62))
    assert reset["latlon"] == latlon((-10, 0))
    assert reset["anchor_cases"] == ["reinitialized"] and reset["stale_resets"] == 1

    # A strict publication cutoff also excludes arrivals exactly at query time.
    assert not stationary.offer(fix("future", STALE_S + 63, STALE_S + 65, 100), seconds(STALE_S + 65))
    assert not stationary.offer(fix("late_older", 61, STALE_S + 63, 100), seconds(STALE_S + 65))
    assert stationary.forecast(seconds(STALE_S + 65))["anchor_cases"] == ["reinitialized"]

    retained = Stationary()
    for hour in (0, 4, 14, 28, 42):
        start = hour * 3600
        assert retained.offer(fix(str(hour), start, start + 1, 0), seconds(start + 2))
    assert retained.forecast(seconds(42 * 3600 + 2))["anchor_cases"] == ["4", "14", "28", "42"]
    assert retained.forecast(seconds(55 * 3600))["anchor_cases"] == ["14", "28", "42"]

    accessed = []

    def archive_loader(scan):
        accessed.append(scan.case)
        assert scan.case in {"prior", "in_flight", "prior_failed"}
        availability, east = {"prior": (400, 2), "in_flight": (1000, 20), "prior_failed": (900, 20)}[scan.case]
        return dict(
            wall_s=0.1,
            modeled_availability_ns=seconds(availability),
            arms={arm: dict(status="estimate", xy=(east, 0)) for arm in ARMS}
            if scan.case != "prior_failed" else {arm: dict(status="insufficient") for arm in ARMS},
        )

    query = Scan("current", seconds(1000), 99)
    schedule = [Scan(name, seconds(start), start) for name, start in (
        ("prior", 0), ("in_flight", 100), ("prior_failed", 500), ("prior_capture_not_complete", 700),
        ("current", 1000), ("future", 1100),
    )]
    result, receipts, not_read = replay([query], schedule, archive_loader)
    assert accessed == ["prior", "in_flight", "prior_failed"]
    assert len(receipts) == 3 and abs(result[0]["anchor_job_wall_s_since_prior_query"] - 0.3) < 1e-12
    assert not_read == ["prior_capture_not_complete", "current", "future"]
    assert result[0]["pending_jobs"] == ["in_flight"]
    for forecast in result[0]["arms"].values():
        assert forecast["kind"] == "forecast" and forecast["rms_hz"] is None
        assert forecast["anchor_cases"] == ["prior"]
        assert forecast["latlon"] == latlon((2, 0))

    return dict(
        no_fix_cold_start_abstains=True,
        single_outlier_east_km=10,
        median_change_after_single_outlier_km=0,
        last_anchor_change_after_single_outlier_km=10,
        relocation_west_km=10,
        forecast_error_after_one_relocated_anchor_km=10,
        stale_outage_empties_history=True,
        post_outage_anchor_reinitializes=True,
        current_future_and_incomplete_capture_graphs_not_read=True,
        exactly_at_cutoff_fix_not_used=True,
        late_older_fix_not_used=True,
        failed_anchor_cost_charged=True,
        count_and_age_limits_enforced=True,
    )


def test_stationary_replay():
    check()


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
