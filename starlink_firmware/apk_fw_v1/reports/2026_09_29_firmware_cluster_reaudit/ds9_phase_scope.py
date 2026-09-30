"""Audit saved phase controls and measure their effect on early Q covariance."""

import json
from pathlib import Path

import numpy as np
from ds9_axis_audit import rotations
from ds9_leakage_transfer import BASE, OLD, source
from ds9_t_quadrature import signs


def phase_correction(values, expected):
    return np.exp(-1j * np.angle(np.mean(values * expected, axis=1)))


def main():
    original_path = OLD / "ds9_tail_phase_transfer.json"
    original = json.loads(original_path.read_text())
    visits = []
    for row in original["rows"]:
        for path, sha in row["input_sha256"].items():
            assert source(Path(path))["sha256"] == sha
        tag, frames = row["tag"], row["evaluation_frames"]
        word_path = OLD / ("ds9_word_audit.json" if tag == "middle" else "ds9_last_word_audit.json")
        states = {}
        for w in json.loads(word_path.read_text())["rows"]:
            if w["accepted"] and w["phase"] is not None and w["last_symbol"] < 242:
                assert states.get(w["frame"], w["phase"]) == w["phase"]
                states[w["frame"]] = w["phase"]
        axes, corrections = [], []
        with np.load(OLD / f"DS9-{tag}-soft.npz") as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            expected = signs([states[f] for f in frames], data["bins0"], range(242, 302))
            for rx in (0, 1):
                z = data[f"z{rx}"][frames]
                correction = phase_correction(z[:, 240:270], expected[:, :30])
                before, after = z[:, 270:300], z[:, 270:300] * correction[:, None]
                errors = [int(((a.real >= 0) != (expected[:, 30:] > 0)).sum())
                          for a in (before, after)]
                assert errors == [row["tail"][rx][k] for k in ("errors_before", "errors_after")]
                angle = float(np.median(abs(np.angle(correction))) * 180 / np.pi)
                np.testing.assert_allclose(angle, row["tail"][rx]["median_abs_rotation_degrees"],
                                           atol=1e-10)
                corrections.append(dict(receiver=rx, errors_before=errors[0],
                                        errors_after=errors[1], count=int(before.size),
                                        median_abs_degrees=angle))
                axes.append((z[:, :6].imag, (z[:, :6] * correction[:, None]).imag))
        rows, controls = [], []
        for index, name in enumerate(("Q_original", "Q_after_tail_phase")):
            for lo, hi in [(0, 6), *[(i, i + 1) for i in range(6)]]:
                scores = rotations(axes[0][index][:, lo:hi], axes[1][index][:, lo:hi])
                controls.append(scores)
                rows.append(dict(component=name, symbols=[lo + 2, hi + 1],
                                 correlation=float(scores[0])))
        maxima = np.abs(controls).max(axis=0)
        for r in rows:
            r["two_excerpt_family_rank"] = min(1., 2 * float(np.mean(
                maxima >= abs(r["correlation"]) - 1e-12)))
        visits.append(dict(visit=tag, frames=frames, rows=rows, tail_validation=corrections))
    pilot_path = OLD / "ds9_symbol_phase_probe.json"
    pilot = json.loads(pilot_path.read_text())
    for path, sha in pilot["input_sha256"].items():
        assert source(Path(path))["sha256"] == sha
    summary = pilot["summary"]
    assert len(pilot["rows"]) == summary["frame_receiver_half_tests"] == 32
    for key in ("before", "after", "header_before", "header_after"):
        np.testing.assert_allclose(np.mean([r[key] for r in pilot["rows"]]), summary[f"mean_{key}"],
                                   atol=1e-12)
    assert sum(r["after"] > r["before"] for r in pilot["rows"]) == summary["improved"] == 0
    output = dict(visits=visits, source=source(original_path),
                  pilot_source=source(pilot_path), pilot_summary=summary,
                  method=source(BASE / "ds9_phase_scope.py"),
                  limitation="Reproduces actual tail sign errors and rotation magnitudes. "
                  "Frozen historical phase estimator uses symbols242–271, not early symbols. "
                  "Later-to-earlier transfer is a noncausal diagnostic. Same-frame state "
                  "selection is paired. New Q comparison is 14 frozen assays per excerpt, "
                  "joint RX1 rotations then two-excerpt Bonferroni. Pilot summary arithmetic "
                  "audited only, raw pilot demodulation not rerun; that probe is DS9-last only "
                  "and reports pilot coherence, not early nonpilot Q. These controls do not "
                  "exclude fast symbol-dependent phase error or establish modulation.")
    (BASE / "local/ds9-phase-scope.json").write_text(json.dumps(output, indent=2) + "\n")
    for v in visits:
        print(v["visit"], [r for r in v["rows"] if r["symbols"] == [2, 7]])


if __name__ == "__main__":
    main()
