"""Score sealed fresh-versus-persistent position and compute-path receipts."""

import gzip
import json
from collections import defaultdict
from statistics import median

from ..__main__ import save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import online_prefix_trial as pilot
from .portable_gate_trials import checksum, compressed_rows
from .prefix_reuse_trial import OUT

METHODS = ("fresh-native-prefix-stop", "persistent-native-prefix-stop")
BINDINGS = ("native_sha256", "catalog_sha256", "track_config_sha256")


def measures(rows, *, persistent):
    return dict(
        calls=len(rows),
        compute_cpu_s=sum(r["worker"]["cpu_s"] for r in rows),
        host_wall_s=sum(r["worker_wall_s"] for r in rows),
        archive_cpu_s=sum(
            r["stages"][
                "increment_decode_and_peaks" if persistent else "archive_and_peak_selection"
            ]["cpu_s"]
            for r in rows
        ),
        catalogue_read_cpu_s=sum(r["stages"]["catalogue_read"]["cpu_s"] for r in rows),
        graph_cpu_s=sum(r["stages"]["graph"]["cpu_s"] for r in rows),
        backend_cpu_s=sum(r["stages"]["clock_backend"]["cpu_s"] for r in rows),
        import_cpu_s=sum(r["stages"]["backend_import"]["cpu_s"] for r in rows),
        native_bytes=sum(
            r["input_delta_bytes"] if persistent else r["counts"]["native_bytes"] for r in rows
        ),
        ephemeris_cells=sum(
            r["ephemeris_cache"]["cells"]
            if persistent
            else sum(
                r["result"]["metrics"].get(k, 0)
                for k in ("coarse_state_evaluations", "fine_state_evaluations")
            )
            for r in rows
        ),
        ephemeris_cpu_s=sum(r["ephemeris_cache"]["cpu_s"] for r in rows) if persistent else None,
        ephemeris_fallbacks=sum(r["ephemeris_cache"]["exact_fallbacks"] for r in rows)
        if persistent
        else None,
        final_cache_bytes=rows[-1]["ephemeris_cache"]["retained_bytes"] if persistent else None,
        peak_mib=max(r["resident_peak_kib"] for r in rows) / 1024,
    )


def position(job, rows, picked, method, truth):
    first = rows[0]
    fit, rule, scores = {}, {}, []
    timeline = pilot.prefix.timeline(rows)
    for arm in ARMS:
        i, why = picked[arm]
        r = rows[i]
        info = r["result"]["arms"][arm]
        fit[arm] = info
        rule[arm] = dict(checkpoint=r["checkpoint"], rule=why, delay_s=timeline[i])
        scores.append(
            dict(
                id=job["id"],
                recording=job["recording"],
                condition=job["condition"],
                arm=arm,
                method=method,
                published=info["latlon"] is not None,
                error_km=distance_km(info["latlon"], truth),
                forced_km=distance_km(info.get("forced_latlon"), truth),
                rf_rms_hz=info.get("rf_rms_hz"),
                **rule[arm],
            )
        )
    pub = any(v["latlon"] is not None for v in fit.values())
    return dict(
        id=job["id"],
        recording=job["recording"],
        condition=job["condition"],
        tile=first["tile"],
        method=method,
        **{k: first[k] for k in BINDINGS},
        result=dict(
            status="ok" if pub else "withheld",
            reason=None if pub else rows[-1]["result"]["reason"],
            boundary="Ordered authenticated native-GLRT prefix replay",
            arms=fit,
            metrics=rule,
        ),
    ), scores


def main():
    lock = json.loads((OUT / "prediction-lock.json").read_bytes())
    for name, digest in lock["files"].items():
        assert checksum(OUT / name) == digest
    data = list(
        map(json.loads, gzip.decompress((OUT / "replay.jsonl.gz").read_bytes()).splitlines())
    )
    truth = pilot.frozen_truth()
    positions, queries, per_arm, cases = [], [], [], []
    for job in data:
        info = {k: job[k] for k in ("id", "recording", "condition")}
        if "fresh" not in job:
            cases.append(dict(info, error=job["error"]))
            continue
        fresh, cached = job["fresh"], job["persistent"]["rows"]
        audit = cached if job["audit"] is None else job["audit"]["rows"]
        parity = [
            dict(p, observation=f["observation_sha256"] == c["observation_sha256"])
            for p, f, c in zip(job["parity"], fresh, audit, strict=True)
        ]
        first = fresh[0]
        site = truth[job["recording"]]
        queries.append(dict(info, truth=site, bindings={k: first[k] for k in BINDINGS}))
        fresh_pick, cached_pick = job["fresh_picked"], job["persistent"]["picked"]
        last = 1 + max(v[0] for v in fresh_pick.values())
        costs = [measures(fresh[:last], persistent=False), measures(cached, persistent=True)]
        cases.append(
            dict(
                info,
                parity=parity,
                same_stop=fresh_pick == cached_pick,
                costs=dict(zip(METHODS, costs, strict=True)),
                persistent_session_wall_s=job["persistent"]["wall_s"],
            )
        )
        for rows, pick, method in zip(
            (fresh, cached), (fresh_pick, cached_pick), METHODS, strict=True
        ):
            pos, scores = position(job, rows, pick, method, site)
            positions.append(pos)
            per_arm.extend(scores)
    groups = defaultdict(list)
    for r in per_arm:
        groups["/".join(r[k] for k in ("method", "condition", "arm"))].append(r)
    metrics = dict(
        (
            key,
            dict(
                n=len(group),
                published=sum(r["published"] for r in group),
                error_km=distribution(r["error_km"] for r in group),
                forced_km=distribution(r["forced_km"] for r in group),
                rf_rms_hz=distribution(r["rf_rms_hz"] for r in group),
            ),
        )
        for key, group in groups.items()
    )
    comparable = [
        r
        for r in cases
        if r.get("same_stop")
        and all(all(v for k, v in p.items() if k != "checkpoint") for p in r["parity"])
    ]
    cost_summary = (
        {
            method: {
                k: median(r["costs"][method][k] for r in comparable)
                for k, v in comparable[0]["costs"][method].items()
                if v is not None
            }
            for method in METHODS
        }
        if comparable
        else {}
    )
    save_json(
        OUT / "scores.json",
        dict(
            cases=cases,
            per_arm=per_arm,
            cohorts=metrics,
            comparable=len(comparable),
            median_cost=cost_summary,
        ),
    )
    pos_file, query_file = OUT / "positions.jsonl.gz", OUT / "figure-queries.json"
    write(pos_file, compressed_rows(positions))
    save_json(query_file, dict(queries=queries))
    save_json(
        OUT / "figure-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files={p.name: checksum(p) for p in (pos_file, query_file)},
        ),
    )


if __name__ == "__main__":
    main()
