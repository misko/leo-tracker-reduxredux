"""Export the checked orbital frequency revision for bounded scalar transfer."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "2026_09_29_orbit_revision_prediction"))
from run import fast, held_error, prediction  # noqa: E402


def main():
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    paths = [
        HERE.parent / "2026_09_29_orbit_revision_prediction/results.json",
        HERE.parent / "2026_09_29_orbit_revision_support/results.json",
        HERE.parent / "2026_09_29_donor_residual_transfer/plan.json",
    ]
    prior, inventory, plan = [json.loads(p.read_text()) for p in paths]
    for name, digest in prior["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest

    def key(c):
        return c["unit_id"], c["session_id"], c["track_id"], c["number"]

    expected = {key(c): c for c in prior["rows"]}
    inventoried = {key(c): c for c in inventory["rows"]}
    reader = TleArchiveReader(Path("/var/lib/leo/tle"))
    refs = {str(r.path): r for r in reader.list_snapshots()}
    cache, rows = {}, []
    max_error = 0.0
    for u in plan["units"]:
        if u["role"] != "target":
            continue
        p = HERE.parent / "2026_09_29_donor_residual_transfer/runs" / u["unit_id"] / "result.json"
        paths.append(p)
        cases = json.loads(p.read_text())["cases"]
        for i, entry in enumerate(u["group"]["inputs"]):
            obs = Path(next(a["path"] for a in entry["artifacts"] if a["kind"] == "observations"))
            document = json.loads(obs.read_text())
            tracks = {t["track_id"]: t for t in document["tracks"]}
            model = fast.Stationary(document, plan["config"])
            x = np.array([*u["x"][:2], u["x"][i + 2]])
            rec, _ = fast.baseline.site(*model.coordinates(x))
            hi = min(
                max(int(np.searchsorted(model.taus, x[2], side="right")), 1), len(model.taus) - 1
            )
            taus = model.taus[[hi - 1, hi]]
            weight = (x[2] - taus[0]) / (taus[1] - taus[0])
            for c in cases:
                if c["session_id"] != entry["session_id"]:
                    continue
                old = expected[key(c)]["arms"]["older_24h"]
                residual = np.asarray(c["residual"])
                mask = np.asarray(c["mask"], bool)
                delta = np.zeros_like(residual)
                product = inventoried[key(c)]["products"]["older_24h"]
                if old["status"] == "ok":
                    path = product["snapshot"]
                    if path not in cache:
                        cache[path] = {
                            r.satellite_number: r
                            for r in parse_element_set_records(reader.read(refs[path]))
                        }
                    record = cache[path][c["number"]]
                    digest = hashlib.sha256(
                        (record.first_line + "\n" + record.second_line + "\n").encode()
                    ).hexdigest()
                    assert digest == old["element_sha256"]
                    pos, vel, ids = propagate_candidate_states(
                        parse_element_sets(record.text),
                        [0],
                        c["start_utc_ns"],
                        np.asarray(c["times"]),
                        taus,
                    )
                    assert ids.tolist() == [0]
                    base = np.asarray(tracks[c["track_id"]]["measured_hz"]) - residual
                    delta = prediction(pos[0], vel[0], rec, weight) - base
                    discrepancy = abs(held_error(residual - delta, mask) - old["held_error"])
                    max_error = max(max_error, discrepancy)
                    assert discrepancy < 1e-6
                    t = np.asarray(c["times"])[mask]
                    z = t - t.mean()
                    d = delta[mask] - delta[mask].mean()
                    assert abs(float(z @ d / (z @ z)) - old["revision_slope_hz_s"]) < 1e-6
                    assert (
                        abs(float(np.sqrt(np.mean(d * d))) - old["revision_centered_rms_hz"]) < 1e-6
                    )
                row = {k: c[k] for k in ("unit_id", "session_id", "track_id", "number", "mask")}
                row.update(
                    residual=residual.tolist(),
                    delta=delta.tolist(),
                    status=old["status"],
                    changed=old.get("changed", False),
                )
                rows.append(row)
        print(u["unit_id"], len(rows), file=sys.stderr, flush=True)
    assert len(rows) == 3983
    paths += [
        HERE / "export.py",
        HERE / "PROTOCOL.md",
        HERE.parent / "2026_09_29_orbit_revision_prediction/run.py",
    ]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    print(json.dumps(dict(hashes=hashes, max_replay_error_hz=max_error, rows=rows), indent=2))


if __name__ == "__main__":
    main()
