"""Known-pilot hard-decision audit at the same post-SSS symbol times.

Unknown header signs are never used as truth. Pilot sign errors are a
BPSK-equivalent calibration check, not a certified header BER measurement.
"""

import json

import numpy as np
from analyze import OUT, demodulate
from recover import geometry, pilot_calibrate, references


def main():
    results = []
    rng = np.random.default_rng(701947)
    for group in ["dual", "best-upper", "best-lower"]:
        out = OUT / group
        inventory = json.loads((out / "inventory.json").read_text())
        recovery = json.loads((out / "recovery.json").read_text())
        streams = []
        for row, record in zip(inventory["exports"], recovery, strict=True):
            edge = row["probe"]["edge"]
            _, pilot_bins, center = geometry(edge)
            _, _, pilots = references(edge)
            raw = np.load(out / (row["name"] + ".npy"))
            x = raw[:, 0].astype(float) + 1j * raw[:, 1]
            values = []
            for frame, epoch in enumerate(record["corrected_frame_epochs_samples"]):
                start = int(epoch) - 100
                sy = demodulate(
                    x[start : start + 13600],
                    1e7,
                    epoch - start,
                    row["candidate"]["fractional_tracking_cfo_hz"],
                    center,
                )
                y, _ = pilot_calibrate(
                    sy, pilots, record["diagnostics"][frame]["phase_slope"], edge
                )
                values.append(y[1:9, pilot_bins] / pilots[:8])
            streams.append(np.array(values))
        # Reuse weights learned from reserved pilot residual variance, rather
        # than choosing weights to minimize these eight-symbol decision errors.
        variance = np.array(
            [np.mean([d["pilot_holdout_evm"] ** 2 for d in r["diagnostics"]]) for r in recovery]
        )
        weights = 1 / variance
        weights /= weights.sum()
        combined = sum(w * z for w, z in zip(weights, streams, strict=True))
        rows = []
        for name, z in zip(["RX0", "RX1", "combined"], [*streams, combined], strict=True):
            errors = z.real < 0
            per_frame = errors.mean(axis=(1, 2))
            boot = rng.choice(per_frame, size=(2000, len(per_frame)), replace=True).mean(axis=1)
            rows.append(
                dict(
                    source=name,
                    known_pilot_observations=z.size,
                    bpsk_equivalent_sign_errors=int(errors.sum()),
                    bpsk_equivalent_sign_error_rate=float(errors.mean()),
                    frame_bootstrap_95_percent=np.quantile(boot, [0.025, 0.975]).tolist(),
                    qpsk_symbol_error_rate=float(np.mean(z.real < abs(z.imag))),
                    error_free_eight_symbol_pilot_blocks=int(np.sum(errors.sum(axis=(1, 2)) == 0)),
                )
            )
        e0, e1 = streams[0] - 1, streams[1] - 1
        covariance = np.vdot(e0, e1) / np.linalg.norm(e0) / np.linalg.norm(e1)
        results.append(
            dict(
                group=group,
                session_id=inventory["exports"][0]["session_id"],
                visit=inventory["exports"][0]["probe"]["visit_index"],
                edge=edge,
                metrics=rows,
                receiver_residual_correlation=[float(covariance.real), float(covariance.imag)],
                limitation="Pilot-equivalent error rate only; header channel, alphabet and coding "
                "can differ. No unknown header bit was treated as truth.",
            )
        )
        np.savez_compressed(
            out / "known-pilot-decision-audit.npz",
            rx0=streams[0],
            rx1=streams[1],
            combined=combined,
            weights=weights,
        )
        print(json.dumps(results[-1]), flush=True)
    (OUT / "survey/decision-audit.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
