import json

import numpy as np
import pytest
import verify_formal_orbit as verification

from leo.analysis.research.regional_doppler import Region


def test_exact_audit_uses_orbit_phase_and_detects_bad_interpolation(tmp_path, monkeypatch):
    paths = {key: tmp_path / f"{key}.json" for key in ("fit", "prior", "reranking")}
    target = {"session_id": "s", "episode_id": "e", "norad": 1, "predicted_phase_s": 0.5}
    paths["prior"].write_text(json.dumps({"strictly_causal": True, "targets": [target]}))
    paths["reranking"].write_text(
        json.dumps(
            {
                "strictly_causal": True,
                "rows": [
                    {
                        "session_id": "s",
                        "episode_id": "e",
                        "best_norad": 1,
                        "capture_start_utc_ns": 7_200_000_000_000,
                        "winning_epoch_utc_ns": 3_600_000_000_000,
                        "winning_collected_utc_ns": 6_000_000_000_000,
                        "winning_tle_text": "test",
                    }
                ],
            }
        )
    )
    paths["fit"].write_text(
        json.dumps(
            {
                "converged": True,
                "x_km": [0, 0],
                "rate_corrections_s_h": {"1": 0.1},
            }
        )
    )
    p = np.array([[7000.0, 1000, 1000]] * 2)
    v = np.array([[0.0, 7, 0]] * 2)
    calls = []

    def exact(cat, ids, capture, times, *, clock_s, orbit_time_s):
        calls.append((clock_s, orbit_time_s))
        return p[None], v[None], [0]

    monkeypatch.setattr(verification, "parse_element_sets", lambda value: value)
    monkeypatch.setattr(verification, "state_arrays", exact)
    states = tmp_path / "states.npz"
    values = dict(
        schema="formal-orbit-phase-state-v1",
        y_hz=np.zeros(2),
        track=np.zeros(2),
        source=np.ones(2),
        age_h=np.ones(2),
        time_s=np.arange(2),
        p_km=p,
        v_km_s=v,
        phase_p_minus_km=p,
        phase_p_plus_km=p,
        phase_v_minus_km_s=v,
        phase_v_plus_km_s=v,
        prior_analysis_digest=verification.digest(paths["prior"]),
        strict_reranking_digest=verification.digest(paths["reranking"]),
    )
    np.savez(states, **values)
    region = Region(40, -75, 100, 100)
    result = verification.verify(states, paths["fit"], paths["prior"], paths["reranking"], region)
    assert result["passed"]
    assert result["observations"] == 2
    assert calls == [(0, 0.6)]
    values["phase_v_plus_km_s"] = v + 0.1
    np.savez(states, **values)
    result = verification.verify(states, paths["fit"], paths["prior"], paths["reranking"], region)
    assert not result["passed"]
    payload = json.loads(paths["fit"].read_text())
    payload["rate_corrections_s_h"] = {}
    paths["fit"].write_text(json.dumps(payload))
    with pytest.raises(KeyError):
        verification.verify(states, paths["fit"], paths["prior"], paths["reranking"], region)
    result = verification.verify(
        states,
        paths["fit"],
        paths["prior"],
        paths["reranking"],
        region,
        allow_unfitted_sources=True,
    )
    assert result["passed"]
    assert result["unfitted_sources_default_zero"]
    assert calls[-1] == (0, 0.5)
