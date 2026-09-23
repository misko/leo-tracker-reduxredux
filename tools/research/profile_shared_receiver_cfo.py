"""Development comparison of common versus source-specific receiver CFO.

Uses the already inspected random groups; this is not fresh validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from leo.storage import RecordingStore
from tools.research.joint_template_source_isolation import _design, seeded_group_split
from tools.research.replay_joint_pilot_isolation import COUNT, FS, ROOT, tones

INPUT = ROOT / "reports/figures/2026_09_23_joint_pilot_isolation"


def fit(response, templates, indices, train, nominal, initial, shared):
    """Profile amplitudes on training samples; optionally constrain receiver CFO."""
    center = float(np.mean(nominal[1] - nominal[0]))

    def residuals(parameters):
        if not shared:
            return np.asarray(parameters).reshape(2, 2)
        a, b, offset = parameters
        return np.array([[a, b], [a, b]]) + np.array(
            [[0.0, 0.0], center + offset - (nominal[1] - nominal[0])]
        )

    def solve(parameters, score_held=False):
        frequencies = residuals(parameters)
        if np.any(abs(frequencies) > 2500):
            return 1e6 + float(np.sum(np.maximum(abs(frequencies) - 2500, 0) ** 2)), []
        total, rows = 0.0, []
        for rx in (0, 1):
            design = _design(templates[rx][:, :, train], indices[train], frequencies[rx], FS)
            coefficients = np.linalg.lstsq(design, response[train, rx], rcond=None)[0]
            residual = response[train, rx] - design @ coefficients
            train_sse = float(np.vdot(residual, residual).real)
            total += train_sse
            if score_held:
                held = _design(templates[rx][:, :, ~train], indices[~train], frequencies[rx], FS)
                error = response[~train, rx] - held @ coefficients
                rows.append(
                    dict(
                        train_sse=train_sse,
                        held_sse=float(np.vdot(error, error).real),
                        coefficients=[[float(z.real), float(z.imag)] for z in coefficients],
                    )
                )
        return total, rows

    if shared:
        offsets = nominal[1] - nominal[0] + initial[1] - initial[0]
        start = np.array([initial[0, 0], initial[0, 1], np.mean(offsets) - center])
    else:
        start = initial.ravel()
    initial_sse = solve(start)[0]
    result = minimize(
        lambda x: solve(x)[0],
        start,
        method="Powell",
        bounds=[(-2500.0, 2500.0)] * len(start),
        options=dict(maxfev=1200, maxiter=8, xtol=0.1, ftol=1e-8),
    )
    # Preserve the initializer if the bounded optimizer found a worse training fit.
    chosen = result.x if result.fun <= initial_sse else start
    score, rows = solve(chosen, True)
    return dict(
        shared=shared,
        residual_cfo_hz=residuals(chosen).tolist(),
        train_sse=score,
        receivers=rows,
        optimizer_success=bool(result.success),
        optimizer_message=str(result.message),
        evaluations=int(result.nfev),
        used_initializer=bool(result.fun > initial_sse),
        boundary_hit=bool(np.any(abs(residuals(chosen)) >= 2499.9)),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = sorted(INPUT.glob("probe-*.json"))
    if len(paths) != 6:
        raise ValueError("six frozen inputs required")
    sources = paths + [
        Path(__file__),
        ROOT / "reports/2026_09_23_shared_cfo_protocol.md",
        ROOT / "tools/research/replay_joint_pilot_isolation.py",
        ROOT / "tools/research/joint_template_source_isolation.py",
    ]
    binding = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    (args.output / "binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    store = RecordingStore.open_read_only(Path("/srv/bulk/leo"))
    try:
        bundle = store.inspect("cap-20260825T010019-89c2889553e0")
        reader = store.reader(bundle, "stream-1", verify=True)
        for index, path in enumerate(paths):
            data = json.loads(path.read_text())
            nominal = np.array(
                [[r["tracking_cfo_hz"] for r in data["nominees"][str(rx)]] for rx in (0, 1)]
            )
            initial = np.array(
                [
                    data["receivers"][str(rx)]["models"]["exact_ab"]["residual_cfo_hz"]
                    for rx in (0, 1)
                ]
            )
            closure = float(np.diff(nominal[1] - nominal[0])[0])
            row = dict(time_s=data["time_s"], nominal_closure_hz=closure)
            if abs(closure) > 10000:
                row["abstention"] = (
                    "no common receiver offset within all four fixed ±2500 Hz residual bounds"
                )
            else:
                raw = reader.read(data["sample_start"], COUNT, receiver_ids=(0, 1))
                if hashlib.sha256(raw.tobytes()).hexdigest() != data["raw_sha256"]:
                    raise ValueError("snippet hash changed")
                iq = (raw[:, :, 0].astype(float) + 1j * raw[:, :, 1].astype(float)) / 32768
                n = np.arange(COUNT)
                mask = (n % 250 >= 16) & (n % 250 < 234)
                train = seeded_group_split(n // 250, seed=20260925 + index)[mask]
                templates = np.array(
                    [
                        [
                            tones(int(r["local_epoch_sample"]), r["tracking_cfo_hz"])
                            for r in data["nominees"][str(rx)]
                        ]
                        for rx in (0, 1)
                    ]
                )[:, :, :, mask]
                row["independent"] = fit(
                    iq[mask], templates, n[mask], train, nominal, initial, False
                )
                row["shared"] = fit(iq[mask], templates, n[mask], train, nominal, initial, True)
                row["held_energy_by_receiver"] = np.sum(abs(iq[mask][~train]) ** 2, axis=0).tolist()
            (args.output / f"probe-{index}.json").write_text(
                json.dumps(row, indent=2, allow_nan=False) + "\n"
            )
            print(json.dumps(row), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
