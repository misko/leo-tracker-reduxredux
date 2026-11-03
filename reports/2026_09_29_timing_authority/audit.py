"""Reconstruct timing brackets without relying on stored qualification flags."""

import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent


def audit(row):
    t = row["timing"]
    if t is None:
        return dict(status="missing")
    offsets = [
        t[p + "_realtime_ns"] - t[p + "_monotonic_ns"]
        for p in ("begin_before", "begin_after", "terminal")
    ]
    earliest = t["begin_before_monotonic_ns"] + min(offsets)
    latest = t["begin_after_monotonic_ns"] + max(offsets)
    estimate = (earliest + latest) // 2
    spread = max(offsets) - min(offsets)
    assert (earliest, estimate, latest) == (
        t["first_sample_earliest_utc_ns"],
        t["first_sample_estimate_utc_ns"],
        t["first_sample_latest_utc_ns"],
    )
    assert latest - earliest == t["first_sample_bracket_width_ns"]
    assert spread == t["maximum_realtime_monotonic_offset_spread_ns"]
    assert t["qualified"] == (max(spread, latest - earliest) <= t["qualification_limit_ns"])
    assert row["observation_start_utc_ns"] == estimate
    lo, hi = (earliest - estimate) / 1e9, (latest - estimate) / 1e9
    tau = row["fitted_tau_s"]
    terminal = row["terminal"]
    assert terminal["first_counter"] == t["session_start_device_sample_counter"]
    return dict(
        status="ok",
        qualified=t["qualified"],
        bracket_width_s=(latest - earliest) / 1e9,
        spread_us=spread / 1e3,
        lower_offset_s=lo,
        upper_offset_s=hi,
        fitted_tau_s=tau,
        outside_distance_s=max(lo - tau, tau - hi, 0),
        sample_rate_hz=t["sample_rate_hz"],
        counter_duration_s=(terminal["final_counter"] - terminal["first_counter"])
        / t["sample_rate_hz"],
    )


def main():
    path = HERE / "metadata.json"
    source = json.loads(path.read_text())
    for name, digest in source["hashes"].items():
        assert hashlib.sha256((HERE.parent.parent / name).read_bytes()).hexdigest() == digest
    rows = [
        dict(unit_id=r["unit_id"], session_id=r["session_id"], **audit(r)) for r in source["rows"]
    ]
    summary = {}
    for ds in ["all", "DS7", "DS8", "DS9"] + sorted({r["unit_id"] for r in rows}):
        selected = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        summary[ds] = dict(
            scans=len(selected),
            timing_present=len(valid),
            qualified=sum(r["qualified"] for r in valid),
            fitted_tau_outside_host_bracket=sum(r["outside_distance_s"] > 0 for r in valid),
        )
        for field in ("bracket_width_s", "spread_us", "outside_distance_s", "counter_duration_s"):
            values = [r[field] for r in valid]
            summary[ds][field] = (
                dict(min=min(values), median=median(values), max=max(values)) if values else None
            )
        if valid:
            lower = max(r["fitted_tau_s"] - r["upper_offset_s"] for r in valid)
            upper = min(r["fitted_tau_s"] - r["lower_offset_s"] for r in valid)
            summary[ds]["posthoc_common_utc_bias"] = dict(
                intersection_lower_s=lower,
                intersection_upper_s=upper,
                feasible=lower <= upper,
                interval_gap_s=max(lower - upper, 0),
            )
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (path, HERE / "audit.py", HERE / "PROTOCOL.md")
    }
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=rows, summary=summary), indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
