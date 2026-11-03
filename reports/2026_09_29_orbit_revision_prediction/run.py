"""Replay pinned orbital baseline and score older causal elements."""

import hashlib
import inspect
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_orbit_revision_support"))
import ds7_fast_baseline_adapter as fast  # noqa: E402
from inventory import epoch_ns  # noqa: E402


def prediction(pos, vel, receiver, weight):
    p = pos[0] * (1 - weight) + pos[1] * weight
    v = vel[0] * (1 - weight) + vel[1] * weight
    unit = p - receiver
    unit /= np.linalg.norm(unit, axis=-1)[:, None]
    return -fast.baseline.REFERENCE_RF_HZ / fast.baseline.LIGHT_KM_S * np.sum(unit * v, axis=-1)


def held_error(residual, mask):
    return float(np.median(abs(residual[~mask] - np.mean(residual[mask]))))


def main():
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    started = time.monotonic()
    paths = [
        HERE.parent / "2026_09_29_orbit_revision_support/results.json",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
        HERE.parent / "2026_09_29_catalogue_recurrence/result.json",
    ]
    inventory, plan, recurrence = [json.loads(p.read_text()) for p in paths]
    for name, digest in inventory["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    wanted = {
        (r["unit_id"], r["session_id"], r["track_id"], r["number"]): r for r in inventory["rows"]
    }
    mapping = {
        (s["session_id"], t["track_id"]): t["numbers"]
        for s in recurrence["scans"]
        for t in s["tracks"]
    }
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    refs = archive.list_snapshots()
    by_path = {str(r.path): r for r in refs}
    cache, hashes, rows = {}, {}, []

    def records(ref):
        key = str(ref.path)
        if key not in cache:
            cache[key] = {
                r.satellite_number: r for r in parse_element_set_records(archive.read(ref))
            }
        return cache[key]

    maxima = np.zeros(3)
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        key = u["unit_id"]
        case_path = HERE.parent / "2026_09_29_donor_residual_transfer/runs" / key / "result.json"
        paths.append(case_path)
        cases = json.loads(case_path.read_text())["cases"]
        by_track = {(c["session_id"], c["track_id"]): c for c in cases}
        for i, entry in enumerate(u["group"]["inputs"]):
            for a in entry["artifacts"]:
                p = Path(a["path"])
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                assert digest == a["sha256"].removeprefix("sha256:")
                hashes[str(p.relative_to(ROOT))] = digest
            manifest = json.loads(
                Path(
                    next(
                        a["path"]
                        for a in entry["artifacts"]
                        if a["kind"] == "candidates" and a["path"].endswith(".json")
                    )
                ).read_text()
            )
            sources = []
            for s in manifest["provider_sources"]:
                ref = next(
                    r
                    for r in refs
                    if r.provider == s["provider"]
                    and r.collected_utc_ns == s["collected_utc_ns"]
                    and r.digest == s["snapshot_sha256"]
                )
                sources.append((ref, records(ref)))
            doc = fast.load_documents(dict(config=plan["config"], inputs=[entry]))[0]
            model = fast.Stationary(doc, plan["config"])
            x = np.asarray([*u["x"][:2], u["x"][i + 2]])
            receiver, _ = fast.baseline.site(*model.coordinates(x))
            hi = min(
                max(int(np.searchsorted(model.taus, x[2], side="right")), 1), len(model.taus) - 1
            )
            lo = hi - 1
            taus = model.taus[[lo, hi]]
            weight = (x[2] - taus[0]) / (taus[1] - taus[0])
            for track in doc["tracks"]:
                c = by_track.get((doc["session_id"], track["track_id"]))
                if c is None:
                    continue
                inv = wanted[key, c["session_id"], c["track_id"], c["number"]]
                choices = [
                    (
                        epoch_ns(rs[c["number"]].first_line),
                        ref.collected_utc_ns,
                        ref.digest,
                        rs[c["number"]],
                    )
                    for ref, rs in sources
                    if c["number"] in rs
                ]
                chosen = max(choices, key=lambda v: v[:3])[-1]
                baseline_sha = hashlib.sha256(
                    (chosen.first_line + "\n" + chosen.second_line + "\n").encode()
                ).hexdigest()
                cat = parse_element_sets(chosen.text)
                p, v, ids = propagate_candidate_states(
                    cat, [0], c["start_utc_ns"], np.asarray(c["times"]), taus
                )
                assert ids.tolist() == [0]
                slot = mapping[c["session_id"], c["track_id"]].index(c["number"])
                dp = float(np.max(abs(p[0] - track["candidate_position_km"][slot, [lo, hi]])))
                dv = float(np.max(abs(v[0] - track["candidate_velocity_km_s"][slot, [lo, hi]])))
                base = prediction(p[0], v[0], receiver, weight)
                residual = np.asarray(c["residual"])
                mask = np.asarray(c["mask"], bool)
                df = float(np.max(abs(track["y"] - base - residual)))
                maxima = np.maximum(maxima, [dp, dv, df])
                assert dp < 1e-8 and dv < 1e-10 and df < 1e-6, (key, c["track_id"], dp, dv, df)
                row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number")}
                row.update(
                    baseline_element_sha256=baseline_sha,
                    baseline_error=held_error(residual, mask),
                    arms={},
                )
                for arm in ("older_6h", "older_24h"):
                    product = inv["products"][arm]
                    if product["record"] is None:
                        row["arms"][arm] = dict(status="missing", held_error=row["baseline_error"])
                        continue
                    ref = by_path[product["snapshot"]]
                    assert ref.sha256 == inventory["snapshots"][product["snapshot"]]["sha256"]
                    record = records(ref)[c["number"]]
                    digest = hashlib.sha256(
                        (record.first_line + "\n" + record.second_line + "\n").encode()
                    ).hexdigest()
                    assert digest == product["record"]["element_sha256"]
                    p, v, ids = propagate_candidate_states(
                        parse_element_sets(record.text),
                        [0],
                        c["start_utc_ns"],
                        np.asarray(c["times"]),
                        taus,
                    )
                    if ids.tolist() != [0]:
                        row["arms"][arm] = dict(
                            status="propagation_failure", held_error=row["baseline_error"]
                        )
                        continue
                    delta = prediction(p[0], v[0], receiver, weight) - base
                    t = np.asarray(c["times"])[mask]
                    z = t - t.mean()
                    dt = delta[mask] - delta[mask].mean()
                    changed = digest != baseline_sha
                    if not changed:
                        assert np.max(abs(delta)) < 1e-6
                    row["arms"][arm] = dict(
                        status="ok",
                        changed=changed,
                        element_sha256=digest,
                        held_error=held_error(residual - delta, mask),
                        revision_slope_hz_s=float(z @ dt / (z @ z)),
                        revision_centered_rms_hz=float(np.sqrt(np.mean(dt * dt))),
                    )
                rows.append(row)
            del doc, model
        print(key, len(rows), flush=True, file=sys.stderr)
    assert len(rows) == 3983
    for p in paths + [
        HERE / "run.py",
        HERE / "PROTOCOL.md",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
        HERE.parent / "2026_09_29_orbit_revision_support/inventory.py",
    ]:
        hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    runtime = {
        str(Path(inspect.getfile(f))): hashlib.sha256(
            Path(inspect.getfile(f)).read_bytes()
        ).hexdigest()
        for f in (TleArchiveReader, parse_element_sets, propagate_candidate_states)
    }
    print(
        json.dumps(
            dict(
                hashes=hashes,
                runtime=runtime,
                max_baseline_difference=dict(
                    position_km=float(maxima[0]),
                    velocity_km_s=float(maxima[1]),
                    frequency_hz=float(maxima[2]),
                ),
                elapsed_seconds=time.monotonic() - started,
                rows=rows,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
