"""Replay fixed q020 weights and export conditional training residual shapes."""

import sys

import numpy as np
from residual import shape
from study import HERE, RECURRENCE, ROOT, read, save

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(HERE.parent / "2026_09_29_unassociated_trend"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402


def main(key):
    plan = read(HERE / "plan.json")
    u = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents(dict(config=plan["config"], inputs=u["group"]["inputs"]))
    model = TrendMixturePosition(docs, plan["config"], baseline.Stationary, 0.2)
    x = np.asarray(u["x"])
    ev = model.evaluate(x, gradient=False, held=True)
    assert abs(ev["score"] - u["training_score"]) < 1e-7
    prior = {(r["session_id"], r["track_id"]): r for r in read(ROOT / u["posterior"])["rows"]}
    mapped = {
        (s["session_id"], t["track_id"]): t
        for s in read(RECURRENCE / "result.json")["scans"]
        for t in s["tracks"]
    }
    for r in ev["rows"]:
        p = prior[r["session_id"], r["track_id"]]
        for field in ("training_log_score", "held_log_score", "signal_responsibility"):
            assert abs(r[field] - p[field]) < 1e-7
        np.testing.assert_allclose(
            r["weights_given_signal"], p["weights_given_signal"], rtol=0, atol=1e-8
        )
    cases = []
    exclusions = []
    for i, (doc, m) in enumerate(zip(docs, model.models, strict=True)):
        for track in doc["tracks"]:
            p = prior[doc["session_id"], track["track_id"]]
            weights = np.asarray(p["weights_given_signal"])
            slots = np.flatnonzero(weights * p["signal_responsibility"] >= 0.5)
            if not len(slots):
                exclusions.append(
                    dict(
                        session_id=doc["session_id"],
                        track_id=track["track_id"],
                        reason="no_strong_candidate",
                    )
                )
                continue
            pred, visible = m.prediction(track, np.r_[x[:2], x[i + 2]])
            for slot in slots:
                assert visible[slot]
                residual = track["y"] - pred[slot]
                s = shape(track["times_s"], residual, track["mask"])
                if s is None:
                    exclusions.append(
                        dict(
                            session_id=doc["session_id"],
                            track_id=track["track_id"],
                            reason="short_training_shape",
                        )
                    )
                    continue
                cases.append(
                    dict(
                        unit_id=key,
                        role=u["role"],
                        session_id=doc["session_id"],
                        track_id=track["track_id"],
                        number=mapped[doc["session_id"], track["track_id"]]["numbers"][slot],
                        receiver_id=track["receiver_id"],
                        rf_hz=track["rf_hz"],
                        start_utc_ns=doc["start_utc_ns"],
                        available_utc_ns=u["available_utc_ns"],
                        candidate_weight=float(weights[slot]),
                        signal_responsibility=p["signal_responsibility"],
                        times=list(track["times_s"]),
                        residual=residual.tolist(),
                        mask=track["mask"].tolist(),
                        shape=s,
                    )
                )
    save(
        HERE / "runs" / key / "result.json",
        dict(
            unit_id=key,
            role=u["role"],
            training_score=ev["score"],
            tracks=len(prior),
            cases=cases,
            exclusions=exclusions,
        ),
    )
    print(key, len(cases), "eligible conditional residual cases", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
