"""Assemble waveform labels, competing orbits and the paired detector benchmark."""

import argparse
import csv
import gzip
import json
from pathlib import Path

import numpy as np

from .full_v5_check import _sha
from .reverse_glrt_reference import ARMS, CASES, REPORT, digest, packed, wrapped
from .reverse_glrt_search import distances, key

PANELS = {
    "initial": "",
    "heldout": "heldout",
    "replication": "replication",
    "quarter-holdout": "quarter-holdout",
}


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write_csv(path, rows):
    if not rows:
        return
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as target:
        out = csv.DictWriter(target, fieldnames=columns)
        out.writeheader()
        out.writerows(rows)


def literal(a, b):
    return bool(
        a
        and b
        and a.get("epoch") is not None
        and b.get("epoch") is not None
        and all(d <= lim for d, lim in zip(distances(a, b), (2, 1000), strict=True))
    )


def legacy(r):
    old = r["incumbent"]
    if old:
        return dict(
            epoch=old["integer_epoch_sample"] + old["fractional_epoch_offset_samples"],
            hz=old["fractional_tracking_cfo_hz"],
            margin=old["fractional_margin"],
        )
    return None


def analyze_orbits(scan, observation, orbits):
    rows = []
    for p in scan["curves"]:
        ctrl = max((q["result"]["held_at_even"] for q in p["controls"]), default=None)
        component = f"{p['component']}/{p['norad']}"
        ranks = {}
        for regime in ("causal", "later"):
            section = (
                orbits.get(scan["case"], {}).get(regime, {}).get(p["arm"], {}).get(component, {})
            )
            nominee = section.get("named") or {}
            other = next(
                (
                    r
                    for r in (section.get("best"), section.get("runner"))
                    if r and r["norad"] != p["norad"]
                ),
                {},
            )
            ranks[regime + "_eligible"] = section.get("eligible")
            ranks[regime + "_named_rank"] = nominee.get("rank")
            ranks[regime + "_named_rms_hz"] = nominee.get("held_rms_hz")
            ranks[regime + "_competitor"] = other.get("norad")
            ranks[regime + "_competitor_rms_hz"] = other.get("held_rms_hz")
        for a in p["aliases"]:
            z = scan["branches"][a["interval"]]
            matched = (
                z["replicated"]
                and abs(z["stock"]["hz"] - a["center"]) <= 2000
                and ctrl is not None
                and z["held_at_even"] > ctrl
            )
            rows.append(
                dict(
                    key=scan["key"],
                    case=scan["case"],
                    visit=scan["visit"],
                    rx=scan["rx"],
                    gate_before=observation["old_pass"],
                    calibration=p["arm"],
                    source=p["source"],
                    component=p["component"],
                    norad=p["norad"],
                    predicted_hz=p["hz"],
                    alias=a["lift"],
                    branch_center_hz=a["center"],
                    strongest_held_control=ctrl,
                    agrees=matched,
                    frequency_hz=z["stock"]["hz"],
                    epoch=z["stock"]["epoch"],
                    margin=z["stock"]["margin"],
                    wrong_at_peak=z["wrong_at_even"],
                    held_at_peak=z["held_at_even"],
                    epoch_difference=z["epoch_delta"],
                    frequency_difference_hz=z["hz_delta"],
                    **ranks,
                )
            )
    return rows


def score_one(report, panel, row, orbit_summary):
    ident = key(row)
    s = read(report / "measurements" / (ident + ".json"))
    if s["row_id"] != row["id"] or s["grid_sha256"] != _sha(report / "grids" / (ident + ".npz")):
        raise ValueError("waveform or grid changed")
    b = s["blind"]
    w = s["wrong_blind"]
    target = b["even"] if b["replicated"] else None
    old = legacy(s)
    orbit = analyze_orbits(s, row, orbit_summary)
    positive = [r for r in orbit if r["agrees"]]
    alternatives = []
    for r in positive:
        q = dict(epoch=r["epoch"], hz=r["frequency_hz"])
        if not any(literal(q, a) for a in alternatives):
            alternatives.append(q)
    arms = {a: sorted({q["norad"] for q in positive if q["calibration"] == a}) for a in ARMS}
    out = dict(
        panel=panel,
        key=ident,
        case=row["case"],
        visit=row["visit"],
        rx=row["rx"],
        channel=row["channel"],
        role=row["stratum"],
        physical_id=row["id"],
        sample_counter=row["counter"],
        edge=row["edge"],
        old_pass=row["old_pass"],
        old_epoch=old["epoch"] if old else None,
        old_hz=old["hz"] if old else None,
        old_margin=old["margin"] if old else None,
        blind_replicated=target is not None,
        blind_epoch=b["even"]["epoch"],
        blind_hz=b["even"]["hz"],
        blind_odd_epoch=b["odd"]["epoch"],
        blind_odd_hz=b["odd"]["hz"],
        blind_stock_margin=b["stock"]["margin"],
        blind_stock_hz=b["stock"]["hz"],
        wrong_code_timing_cfo_agree=w["epoch_delta"] <= 2 and w["hz_delta"] <= 1000,
        old_signed_match=literal(old, target) if target else None,
        orbit_waveform_cells=len(alternatives),
        fitting_norads=" ".join(map(str, arms["fitted_c"])),
        zero_norads=" ".join(map(str, arms["c0"])),
        orbit_alias_ambiguous=len(alternatives) > 1,
        signed_iq=s["signed_iq"],
    )
    light_file = report / "light" / (ident + ".json")
    light_result = read(light_file) if light_file.is_file() else None
    if light_result and light_result["iq_sha256"] != s["signed_iq"]:
        raise ValueError("compact receiver used a different input")
    light = light_result["methods"] if light_result else None
    if light:
        out["old_cpu_s"] = light["original"]["lane_cpu_s"]
    else:
        out["old_cpu_s"] = sum(
            (e["coarse_cpu_ns"] + e["verify_cpu_ns"]) * 1e-9
            for e in s["cpu"]["original_stages"]
            if e["lane"] == s["rx"]
        )
    methods = {"eight": s["compact"]["winner"]}
    if light:
        methods.update(eight=light["eight"]["winner"], four=light["four"]["winner"])
        for m in ("eight", "four"):
            out[m + "_cpu_s"] = light[m]["lane_cpu_s"]
            out[m + "_paired_old_cpu_s"] = light["original"]["lane_cpu_s"]
    else:
        out["eight_cpu_s"] = s["cpu"]["compact_mono"]["cpu_s"]
    sf = report / "stack" / (ident + ".json")
    if sf.exists():
        stack = read(sf)
        if stack["iq"] != s["signed_iq"]:
            raise ValueError("stack received a different input")
        methods["stack"] = stack["winner"]
        out["stack_cpu_s"] = stack["cpu_s"]
        out["stack_paired_old_cpu_s"] = stack["original_cpu_s"]
    quarter_file = report / "quarter" / (ident + ".json")
    if quarter_file.exists():
        trial = read(quarter_file)
        if trial["signed_iq"] != s["signed_iq"]:
            raise ValueError("quarter-rate receiver used a different input")
        measured = trial["methods"]["real"]
        checked = measured["original"]["winner"]
        if (old is None) != (checked is None) or (old and not literal(old, checked)):
            raise ValueError("original receiver changed on paired trial")
        for method in ("stack", "quarter"):
            methods[method] = measured[method]["winner"]
            out[method + "_cpu_s"] = measured[method]["cpu_s"]
            out[method + "_paired_old_cpu_s"] = measured["original"]["cpu_s"]
        out["old_cpu_s"] = measured["original"]["cpu_s"]
        for method in ("original", "stack", "quarter"):
            out[method + "_phase_null_published"] = (
                trial["methods"]["phase_null"][method]["winner"] is not None
            )
    for method, found in methods.items():
        out[method + "_published"] = found is not None
        out[method + "_hz"] = found["hz"] if found else None
        out[method + "_epoch"] = found["epoch"] if found else None
        out[method + "_signed_match"] = literal(found, target) if target else None
    return out, [dict(panel=panel, **r) for r in orbit]


def detector_summary(rows):
    results = []
    for panel in PANELS:
        group = [r for r in rows if r["panel"] == panel]
        for method in ("old", "eight", "four", "stack", "quarter"):
            fields = [r for r in group if method + "_cpu_s" in r]
            ref = [r for r in fields if r["blind_replicated"]]
            if not fields:
                continue
            hits = [r for r in ref if r[method + "_signed_match"]]
            lat = np.array([r[method + "_cpu_s"] for r in fields]) * 1000
            old = (
                np.array([r.get(method + "_paired_old_cpu_s", r["old_cpu_s"]) for r in fields])
                * 1000
            )
            times = np.percentile(lat, [50, 95])
            published = sum(
                r["old_pass" if method == "old" else method + "_published"] for r in fields
            )
            results.append(
                dict(
                    panel=panel,
                    method=method,
                    all_probes=len(fields),
                    published=published,
                    reference_probes=len(ref),
                    signed_matches=len(hits),
                    signed_match_given_reference=len(hits) / len(ref) if ref else None,
                    median_cpu_ms=times[0],
                    p95_cpu_ms=times[1],
                    median_paired_cpu_ratio=float(np.median(lat / old)),
                    total_cpu_ratio=float(np.sum(lat) / np.sum(old)),
                )
            )
    return results


def expanded(report):
    table = []
    summary = []
    paths = sorted((report / "stock").glob("DS*.json"))
    for path in paths:
        s = read(path)
        published = []
        for center in s["centers"]:
            row = center["regions"]["band"]
            p = row["peaks"][0]
            if (
                row["official"]["gate"]
                and literal(row["even"], row["odd"])
                and literal(p, row["official"])
                and literal(p, row["even"])
            ):
                published.append(p)
        narrow = sorted(published, key=lambda p: -p["margin"])
        strong = []
        for p in narrow:
            if not any(literal(p, q) for q in strong):
                strong.append(p)
        for t in s["targets"]:
            found = next(i for i in s["centers"] if i["base"] == t["base"])["regions"].get(
                t["tube"]
            )
            if found is None:
                continue
            p = found["peaks"][0]
            native = found["official"]
            stable = (
                native["gate"]
                and literal(found["even"], found["odd"])
                and literal(p, native)
                and literal(p, found["even"])
                and abs(native["hz"] - t["center"]) <= 2000
            )
            table.append(
                dict(
                    key=s["key"],
                    source=t["source"],
                    component=t["component"],
                    norad=t["norad"],
                    arm=t["arm"],
                    alias=t["lift"],
                    predicted_hz=t["center"],
                    receiver_hz=p["hz"],
                    epoch=p["epoch"],
                    margin=p["margin"],
                    fractional_hz=native["hz"],
                    fractional_epoch=native["epoch"],
                    fractional_margin=native["margin"],
                    stock_split_agrees=stable,
                )
            )
        allbest = max(
            (c["regions"]["band"]["peaks"][0] for c in s["centers"]), key=lambda p: p["margin"]
        )
        summary.append(
            dict(
                key=s["key"],
                centers=s["center_count"],
                integer_cells=s["center_count"] * s["integer_epochs"] * s["residual_bins"],
                lo_hz=s["interval_hz"][0],
                hi_hz=s["interval_hz"][1],
                seconds=s["cpu_s"],
                stable_cells=len(strong),
                strongest_hz=allbest["hz"],
                strongest_margin=allbest["margin"],
                strongest_stable_hz=strong[0]["hz"] if strong else None,
                outside_stable=sum(abs(q["hz"]) > 800000 for q in strong),
                **s["double_oracle_max_delta"],
            )
        )
    return summary, table


def association_summary(source):
    summaries = read(source / "orbit-summary.json.gz")
    output = []
    for case, banks in summaries.items():
        for regime, arms in banks.items():
            for arm, tracks in arms.items():
                for q in tracks.values():
                    n = q.get("named") or {}
                    best = q.get("best") or {}
                    runner = q.get("runner") or {}
                    output.append(
                        dict(
                            case=case,
                            regime=regime,
                            arm=arm,
                            component=q["component"],
                            named_norad=q["named_norad"],
                            points=q["points"],
                            eligible=q.get("eligible"),
                            named_rank=n.get("rank"),
                            named_held_rms_hz=n.get("held_rms_hz"),
                            best_norad=best.get("norad"),
                            best_rms_hz=best.get("held_rms_hz"),
                            runner_norad=runner.get("norad"),
                            runner_rms_hz=runner.get("held_rms_hz"),
                            status=q["status"],
                        )
                    )
    return output


def draw(report, rows, orbit):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    witnesses = [("DS26-0036-v0408-rx0", 67850), ("DS26-0237-v3185-rx1", 58619)]
    f, axes = plt.subplots(2, 2, figsize=(11, 6.2), layout="constrained")
    for (ident, sat), ax in zip(witnesses, axes, strict=True):
        row = next(r for r in rows if r["key"] == ident)
        members = [
            r
            for r in orbit
            if r["key"] == ident and r["calibration"] == "fitted_c" and r["norad"] == sat
        ]
        orig = next(r for r in members if r["alias"] == 0)
        meta = next(r for r in read(report / "roster.json") if key(r) == ident)
        t0, ref = meta["time_s"], orig["predicted_hz"]
        ds = read(report / "manifest.json")
        case = next(c for c in ds["cases"] if c["case"] == row["case"])
        samples = []
        with gzip.open(report / "opportunities.jsonl.gz", "rt") as stream:
            for line in stream:
                p = json.loads(line)
                if (
                    p["case"] != case["case"]
                    or abs(p["time_s"] - t0) > 8
                    or p["rx"] != meta["rx"]
                    or p["channel"] != meta["channel"]
                ):
                    continue
                own = p["owners"]["fitted_c"]
                if own and own["component"] == orig["component"] and own["norad"] == sat:
                    samples.append(
                        (
                            p["time_s"] - t0,
                            wrapped(own["measured_cfo_hz"] - ref) / 1e3,
                            wrapped(own["prediction_hz"] - ref) / 1e3,
                        )
                    )
        x, y, pred = map(np.array, zip(*sorted(samples), strict=True))
        ax[0].plot(x, pred, label="v5 satellite prediction", color="#254e76")
        ax[0].scatter(x, y, label="v5 measurements", s=22, color="#254e76")
        literal_peak = next(r for r in members if r["alias"] == 0 and r["agrees"])
        ax[0].scatter(
            [0],
            [(literal_peak["frequency_hz"] - ref) / 1e3],
            marker="D",
            s=58,
            color="#cf5d30",
            label="Recovered from raw I/Q",
            zorder=4,
        )
        ax[0].set(
            title=f"{row['case']} · visit {row['visit']} · NORAD {sat}",
            xlabel="Time from missed visit (s)",
            ylabel="CFO relative to prediction (kHz)",
        )
        grid = np.load(report / "grids" / (ident + ".npz"))
        hz = grid["hz"] / 1000
        for i, (color, label) in enumerate([("#246a76", "Even frames"), ("#a4a4aa", "Odd frames")]):
            vals = 10 * np.log10(np.maximum(grid["exact_score"][:, i, 0], 1e-12))
            ax[1].plot(hz, vals, color=color, lw=0.9, alpha=0.85, label=label)
        for j, r in enumerate(q for q in members if q["agrees"]):
            ax[1].axvline(
                r["frequency_hz"] / 1000,
                color="#cf5d30",
                ls="--",
                lw=1.5,
                label="Orbit-compatible peak" if j == 0 else None,
            )
        ax[1].set(
            title="Full timing search at each carrier",
            xlabel="Signed CFO (kHz)",
            ylabel="Peak normalized pilot power (dB)",
            xlim=(-810, 810),
        )
        for a in ax:
            a.spines[["right", "top"]].set_visible(False)
            a.grid(alpha=0.22)
    for a in axes[0]:
        a.legend(fontsize=8, loc="best")
    f.savefig(report / "reverse-search.png", dpi=160)
    plt.close(f)


def run(report):
    rows, orbit = [], []
    visits = set()
    complete = report / "complete-associations"
    full_orbits = (
        read(complete / "orbit-summary.json.gz")
        if (complete / "orbit-summary.json.gz").exists()
        else {}
    )
    for panel, sub in PANELS.items():
        path = report / sub
        cases = read(path / "manifest.json")
        roster = read(path / "roster.json")
        if digest((path / "roster.json").read_bytes()) != cases["roster_sha256"]:
            raise ValueError("roster mismatch")
        orbital = full_orbits or (
            read(path / "orbit-summary.json.gz")
            if (path / "orbit-summary.json.gz").exists()
            else {}
        )
        for r in roster:
            visit = r["case"], r["visit"]
            if visit in visits:
                raise ValueError("physical visit reused across panels")
            visits.add(visit)
            record, hypotheses = score_one(path, panel, r, orbital)
            rows.append(record)
            orbit.extend(hypotheses)
    measures = detector_summary(rows)
    out, candidates = expanded(report)
    write_csv(report / "references.csv", rows)
    write_csv(report / "orbit-candidates.csv", orbit)
    write_csv(report / "detector-comparison.csv", measures)
    write_csv(report / "expanded-coverage.csv", out)
    write_csv(report / "expanded-orbit-candidates.csv", candidates)
    if full_orbits:
        write_csv(report / "all-associations.csv", association_summary(complete))
    draw(report, rows, orbit)
    result = dict(
        calibration_arms=ARMS,
        recordings=CASES,
        opportunities=len(rows),
        blind_replicated=sum(r["blind_replicated"] for r in rows),
        matched=measures,
        expanded_probes=len(out),
        expanded_cells=sum(r["integer_cells"] for r in out),
    )
    (report / "summary.json").write_bytes(packed(result) + b"\n")
    print(
        "waveform rows",
        len(rows),
        "broad stock searches",
        len(out),
        "alias rows",
        len(orbit),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=REPORT)
    run(p.parse_args().report)
