"""Exploratory temporal preselection metric; never acquisition authority."""

import hashlib, json
from pathlib import Path
import numpy as np

BASE = Path(__file__).parent
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def score(raw, lag):
    a = raw[:-lag].astype(np.int64)
    b = raw[lag:].astype(np.int64)
    real = int(np.sum(a[:, 0] * b[:, 0] + a[:, 1] * b[:, 1]))
    imag = int(np.sum(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]))
    ea = int(np.sum(a * a))
    eb = int(np.sum(b * b))
    exact = (real * real + imag * imag) / max(ea * eb, 1)
    za = a[:, 0].astype(float) + 1j * a[:, 1]
    zb = b[:, 0].astype(float) + 1j * b[:, 1]
    floating = abs(np.vdot(za, zb)) ** 2 / max(
        float(np.vdot(za, za).real * np.vdot(zb, zb).real), 1
    )
    np.testing.assert_allclose(exact, floating, rtol=2e-12, atol=2e-15)
    return dict(lag=lag, pairs=len(a), power=exact, real=real, imag=imag, energy_a=ea, energy_b=eb)


cases = []
prior = json.loads((BASE / "combined-pilot-controls-v1/result.json").read_text())
for case in prior["cases"]:
    label = f"{case['label']}-{case['number']}"
    path = BASE / "combined-pilot-controls-v1" / label / "iq.ci16"
    assert digest(path) == case["input_sha256"]
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 2)[:14000]
    cases.append(
        dict(
            label=label,
            input_sha256=digest(path),
            metrics=[score(raw, n) for n in (3333, 6667, 10000)],
        )
    )
for capture in ("live-scan64-30-v1", "live-scan64-60-v1", "live-scan64-60-v2"):
    root = BASE / capture
    path = root / "scan.iq.ci16"
    op = json.loads((root / "operator.json").read_text())
    assert digest(path) == op["artifacts"]["scan.iq.ci16"]["sha256"]
    raw = np.fromfile(path, dtype="<i2").reshape(-1, 14000, 2)
    workers = [json.loads(line) for line in (root / "worker.jsonl").read_text().splitlines()]
    for n, cut in enumerate(raw, 1):
        past = [r for r in workers if r.get("attempt") == n and r["kind"] == 3]
        cases.append(
            dict(
                label=f"{capture}-attempt{n}",
                input_sha256=digest(path),
                offset=(n - 1) * 14000,
                accepted_past=sum(r["accepted"] for r in past),
                metrics=[score(cut, lag) for lag in (3333, 6667, 10000)],
            )
        )
result = dict(
    scope="exploratory_repetition_window_preselection",
    new_rf_samples=0,
    threshold_selected=False,
    acquisition_qualified=False,
    cases=cases,
    script_sha256=digest(Path(__file__)),
)
with (BASE / "repetition-window-selection-v1.json").open("x") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
for case in cases:
    print(case["label"], [round(r["power"], 6) for r in case["metrics"]], case.get("accepted_past"))
