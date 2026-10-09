"""Fixed-state continuity diagnostic on orbit-blind prepared bootstrap tracks."""

import hashlib
import sys
from pathlib import Path

import numpy as np
from continuity import describe

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import load_member, read, write_json  # noqa: E402


def main():
    plan = read(HERE / "protocol.json")
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first continuity audit")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    model = make_model(case, doc, 1, census["candidate_union"])
    completed = read(REPORTS / "2026_10_09_position_error_iter72/summary.json")
    sources = []
    for arm, m in completed["metrics"].items():
        for name, key in (
            ("operational-winner", "hard_all_winner"),
            ("closest-evaluation-only", "closest_qualified_evaluation_only"),
        ):
            sources.append(
                dict(label=name, arm=arm, source_index=m[key]["index"], fit=m[key]["fit"])
            )
    for i, row in enumerate(
        read(REPORTS / "2026_10_09_position_error_iter52/results.json")["rows"]
    ):
        sources.append(
            dict(
                label="historical-" + row["hypothesis"],
                arm=row["arm"],
                source_index=i,
                fit=row["fit"],
            )
        )
    tracks = [np.asarray(t, dtype=int) for t in case.prepared.bootstrap_tracks]
    permutations = [
        np.random.default_rng(plan["seed"] + i).permutation(len(t)) for i, t in enumerate(tracks)
    ]
    meta = []
    for i, t in enumerate(tracks):
        obs = model.observations
        assert np.all(np.diff(obs.times_s[t]) >= 0)
        assert len(set(obs.receiver[t])) == len(set(obs.rf_hz[t])) == 1
        meta.append(
            dict(
                index=i,
                windows=t.tolist(),
                receiver=int(obs.receiver[t[0]]),
                rf_hz=float(obs.rf_hz[t[0]]),
                span_s=float(np.ptp(obs.times_s[t])),
            )
        )
    rows = []
    for source in sources:
        fit = source["fit"]
        v = np.asarray(fit["vector"])
        clock = np.asarray(fit["clock_coefficients"])
        score, _, _, terms = model.evaluate_joint(v, clock)
        np.testing.assert_allclose(score, fit["objective"], atol=1e-6, rtol=0)
        stats = []
        for i, t in enumerate(tracks):
            p = terms.responsibilities[t]
            stats.append(dict(index=i, ordered=describe(p), permuted=describe(p[permutations[i]])))
        rows.append(
            dict(
                label=source["label"],
                arm=source["arm"],
                source_index=source["source_index"],
                converged=fit["converged"],
                tracks=stats,
            )
        )
    all_indices = np.concatenate(tracks)
    write_json(
        HERE / "results.json",
        dict(
            rows=rows,
            tracks=meta,
            observations=len(model.observations.times_s),
            unique_track_windows=len(set(all_indices.tolist())),
            track_memberships=len(all_indices),
            seed=plan["seed"],
        ),
    )
    print("Audited", len(sources), "fixed states on", len(tracks), "orbit-blind tracks", flush=True)


if __name__ == "__main__":
    main()
